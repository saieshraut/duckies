# Copyright (c) 2026, Duckie's Sports Cafe
"""Razorpay recharge flow.

Golden rule: the wallet is credited ONLY from the signature-verified webhook
(payment.captured) — never from the browser's success callback, which can be
spoofed or lost. The webhook is idempotent, so Razorpay's retries are safe.

Configure in the Razorpay dashboard:
  Webhook URL   : https://<your-site>/api/method/duckies.payments.razorpay.webhook
  Active events : payment.captured (add payment.failed if you want failures marked)
  Secret        : same value as Duckies Settings → Razorpay Webhook Secret
"""

import hashlib
import hmac
import json

import frappe
import requests
from frappe import _
from frappe.utils import flt

from duckies.wallet.api import apply_recharge, get_customer_for_user

RAZORPAY_API = "https://api.razorpay.com/v1"


def _settings():
    return frappe.get_cached_doc("Duckies Settings")


def _auth():
    s = _settings()
    key_id = s.razorpay_key_id
    secret = s.get_password("razorpay_key_secret", raise_exception=False)
    if not (key_id and secret):
        frappe.throw(_("Razorpay keys are not configured in Duckies Settings."))
    return (key_id, secret)


# --------------------------------------------------------------------------
# Step 1: customer asks to recharge → create Razorpay Order
# --------------------------------------------------------------------------

@frappe.whitelist()
def create_recharge_order(amount):
    customer = get_customer_for_user()
    amount = flt(amount)
    s = _settings()
    if amount < flt(s.min_recharge_amount):
        frappe.throw(_("Minimum recharge is {0}.").format(s.min_recharge_amount))

    req = frappe.get_doc({
        "doctype": "Recharge Request",
        "customer": customer,
        "amount": amount,
        "status": "Pending",
        "channel": "Online",
    }).insert(ignore_permissions=True)

    resp = requests.post(
        f"{RAZORPAY_API}/orders",
        auth=_auth(),
        json={
            "amount": int(round(amount * 100)),  # paise
            "currency": "INR",
            "receipt": req.name,
            "notes": {"recharge_request": req.name, "customer": customer},
        },
        timeout=15,
    )
    if resp.status_code != 200:
        frappe.log_error(title="Razorpay order failed", message=resp.text)
        frappe.throw(_("Could not start the payment. Please try again."))

    order = resp.json()
    req.db_set("razorpay_order_id", order["id"])

    from duckies.wallet.api import get_applicable_bonus
    bonus, offer = get_applicable_bonus(amount)

    return {
        "recharge_request": req.name,
        "order_id": order["id"],
        "key_id": _auth()[0],
        "amount": order["amount"],       # paise, pass straight to Checkout
        "currency": order["currency"],
        "expected_bonus": bonus,
        "offer": offer,
        "name": "Duckie's Sports Cafe",
        "description": _("Wallet recharge of ₹{0}").format(amount),
    }


# --------------------------------------------------------------------------
# Step 2: Razorpay calls us back (source of truth)
# --------------------------------------------------------------------------

@frappe.whitelist(allow_guest=True, methods=["POST"])
def webhook():
    payload = frappe.request.data or b""
    signature = frappe.request.headers.get("X-Razorpay-Signature", "")

    secret = _settings().get_password("razorpay_webhook_secret",
                                      raise_exception=False)
    if not secret:
        frappe.log_error(title="Razorpay webhook: secret not configured")
        frappe.throw(_("Webhook not configured."), frappe.PermissionError)

    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        frappe.log_error(title="Razorpay webhook: bad signature",
                         message=payload.decode(errors="replace")[:2000])
        frappe.throw(_("Invalid signature."), frappe.PermissionError)

    event = json.loads(payload)
    etype = event.get("event")
    entity = (event.get("payload", {}).get("payment", {}).get("entity", {}))
    order_id = entity.get("order_id")
    payment_id = entity.get("id")

    if not order_id:
        return "ignored"

    req_name = frappe.db.get_value("Recharge Request",
                                   {"razorpay_order_id": order_id}, "name")
    if not req_name:
        frappe.log_error(title="Razorpay webhook: unknown order",
                         message=order_id)
        return "unknown-order"

    if etype == "payment.captured":
        settle_recharge_request(req_name, payment_id=payment_id)
    elif etype == "payment.failed":
        if frappe.db.get_value("Recharge Request", req_name, "status") == "Pending":
            frappe.db.set_value("Recharge Request", req_name, "status", "Failed")

    return "ok"


def settle_recharge_request(req_name: str, payment_id: str | None = None,
                            remarks: str | None = None):
    """Idempotently credit the wallet (+bonus) and post accounting for a
    recharge. Shared by webhook and offline recharges."""
    req = frappe.get_doc("Recharge Request", req_name, for_update=True)
    if req.status == "Paid":
        return req  # webhook retry — already settled

    txn, bonus_txn, bonus = apply_recharge(
        req.customer, req.amount,
        "Recharge Request", req.name,
        remarks or _("Wallet recharge via {0}").format(req.channel),
    )

    req.db_set("status", "Paid")
    if payment_id:
        req.db_set("razorpay_payment_id", payment_id)
    req.db_set("wallet_transaction", txn.name)
    req.db_set("bonus_amount", bonus)
    if bonus_txn:
        req.db_set("bonus_wallet_transaction", bonus_txn.name)

    _post_recharge_accounting(req, bonus)
    return req


def _post_recharge_accounting(req, bonus: float):
    """Dr Bank/Razorpay, Cr Wallet Liability (cash portion); Dr Promo Expense,
    Cr Wallet Liability (bonus portion). Failure is logged, never blocks the
    customer's credit — accounts can repost from the log."""
    s = _settings()
    if not (s.company and s.wallet_liability_account and s.deposit_account):
        frappe.log_error(
            title=f"Recharge accounting skipped for {req.name}",
            message="Configure company/accounts in Duckies Settings, then post a JE manually.",
        )
        return
    try:
        accounts = [
            {"account": s.deposit_account, "debit_in_account_currency": flt(req.amount)},
            {"account": s.wallet_liability_account,
             "credit_in_account_currency": flt(req.amount)},
        ]
        if bonus > 0 and s.promo_expense_account:
            accounts += [
                {"account": s.promo_expense_account,
                 "debit_in_account_currency": flt(bonus)},
                {"account": s.wallet_liability_account,
                 "credit_in_account_currency": flt(bonus)},
            ]
        je = frappe.get_doc({
            "doctype": "Journal Entry",
            "company": s.company,
            "posting_date": frappe.utils.today(),
            "user_remark": f"Wallet recharge {req.name} ({req.customer})",
            "accounts": accounts,
        })
        je.flags.ignore_permissions = True
        je.insert()
        je.submit()
        req.db_set("journal_entry", je.name)
    except Exception:
        frappe.log_error(title=f"Recharge JE failed for {req.name}",
                         message=frappe.get_traceback())
