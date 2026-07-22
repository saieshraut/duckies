# Copyright (c) 2026, Duckie's Sports Cafe
"""Core wallet ledger — bucketed (Cash + Bonus).

Compliance model (RBI closed-system PPI + CBIC voucher circulars):
  * Cash bucket  = real money the customer loaded. Refundable to source.
  * Bonus bucket = promotional credit. NON-refundable, expires with wallet.
  * Spends consume Bonus first, then Cash (standard promo hygiene).
  * No cash withdrawal, no third-party payment, no wallet-to-wallet transfer
    — none of those code paths exist, by design.

Every rupee in or out of a wallet MUST pass through credit()/debit(), which
lock the Customer row so concurrent spends can't both pass the check.
"""

import frappe
from frappe import _
from frappe.utils import flt, now_datetime


# --------------------------------------------------------------------------
# Identity
# --------------------------------------------------------------------------

def get_customer_for_user(user: str | None = None) -> str:
    user = user or frappe.session.user
    if not user or user == "Guest":
        frappe.throw(_("Please log in first."), frappe.AuthenticationError)
    customer = frappe.db.get_value("Customer", {"custom_user": user}, "name")
    if not customer:
        frappe.throw(_("No customer profile is linked to this account. "
                       "Please contact the cafe front desk."))
    return customer


# --------------------------------------------------------------------------
# Balances
# --------------------------------------------------------------------------

def get_buckets(customer: str) -> tuple:
    """Return (cash_balance, bonus_balance)."""
    row = frappe.db.get_value(
        "Customer", customer,
        ["custom_wallet_cash", "custom_wallet_bonus"], as_dict=True) or {}
    return flt(row.get("custom_wallet_cash")), flt(row.get("custom_wallet_bonus"))


def get_balance(customer: str) -> float:
    cash, bonus = get_buckets(customer)
    return cash + bonus


def lock_customer(customer: str) -> None:
    frappe.db.sql("SELECT name FROM `tabCustomer` WHERE name = %s FOR UPDATE",
                  (customer,))


def _touch_activity(customer: str) -> None:
    frappe.db.set_value("Customer", customer, "custom_wallet_last_activity",
                        now_datetime(), update_modified=False)


# --------------------------------------------------------------------------
# Ledger primitive
# --------------------------------------------------------------------------

def _write_txn(customer, amount, txn_type, direction, bucket,
               cash_after, bonus_after, ref_dt=None, ref_dn=None, remarks=None):
    txn = frappe.get_doc({
        "doctype": "Wallet Transaction",
        "customer": customer,
        "transaction_type": txn_type,
        "direction": direction,
        "bucket": bucket,
        "amount": flt(amount),
        "cash_balance_after": cash_after,
        "bonus_balance_after": bonus_after,
        "balance_after": cash_after + bonus_after,
        "reference_doctype": ref_dt,
        "reference_name": ref_dn,
        "remarks": remarks,
    })
    txn.flags.ignore_permissions = True
    txn.insert()
    txn.submit()
    return txn


def _persist(customer, cash_after, bonus_after):
    frappe.db.set_value("Customer", customer, {
        "custom_wallet_cash": cash_after,
        "custom_wallet_bonus": bonus_after,
        "custom_wallet_balance": cash_after + bonus_after,
    }, update_modified=False)


def credit(customer, amount, txn_type, bucket="Cash",
           ref_dt=None, ref_dn=None, remarks=None):
    """Add to a single bucket (Recharge/Bonus/Refund-in/Adjustment)."""
    amount = flt(amount)
    if amount <= 0:
        frappe.throw(_("Credit amount must be positive."))
    if bucket not in ("Cash", "Bonus"):
        frappe.throw(_("Invalid wallet bucket."))
    lock_customer(customer)
    cash, bonus = get_buckets(customer)
    if bucket == "Cash":
        cash += amount
    else:
        bonus += amount
    txn = _write_txn(customer, amount, txn_type, "Credit", bucket,
                     cash, bonus, ref_dt, ref_dn, remarks)
    _persist(customer, cash, bonus)
    _touch_activity(customer)
    return txn


def debit(customer, amount, txn_type, ref_dt=None, ref_dn=None, remarks=None):
    """Spend across buckets: Bonus first, then Cash. May write two ledger
    rows (one per bucket touched). Returns the list of txns."""
    amount = flt(amount)
    if amount <= 0:
        frappe.throw(_("Debit amount must be positive."))
    lock_customer(customer)
    cash, bonus = get_buckets(customer)

    if amount > cash + bonus + 0.005:  # paise tolerance
        frappe.throw(
            _("Insufficient wallet balance. Available: {0}, required: {1}. "
              "Please recharge your wallet.").format(
                frappe.format_value(cash + bonus, {"fieldtype": "Currency"}),
                frappe.format_value(amount, {"fieldtype": "Currency"}),
            ),
            title=_("Insufficient Balance"),
        )

    txns = []
    from_bonus = min(bonus, amount)
    if from_bonus > 0:
        bonus -= from_bonus
        txns.append(_write_txn(customer, from_bonus, txn_type, "Debit", "Bonus",
                               cash, bonus, ref_dt, ref_dn, remarks))
    from_cash = amount - from_bonus
    if from_cash > 0:
        cash -= from_cash
        txns.append(_write_txn(customer, from_cash, txn_type, "Debit", "Cash",
                               cash, bonus, ref_dt, ref_dn, remarks))
    _persist(customer, cash, bonus)
    _touch_activity(customer)
    return txns


def has_txn_for_reference(customer, direction, ref_dt, ref_dn) -> bool:
    return bool(frappe.db.exists("Wallet Transaction", {
        "customer": customer, "direction": direction, "docstatus": 1,
        "reference_doctype": ref_dt, "reference_name": ref_dn,
    }))


# --------------------------------------------------------------------------
# Recharge + offers
# --------------------------------------------------------------------------

def get_applicable_bonus(amount: float):
    amount = flt(amount)
    today = frappe.utils.today()
    offers = frappe.get_all(
        "Recharge Offer",
        filters={"is_active": 1, "min_recharge_amount": ("<=", amount)},
        fields=["name", "bonus_type", "bonus_amount", "bonus_percent",
                "valid_from", "valid_to"])
    best, best_offer = 0.0, None
    for o in offers:
        if o.valid_from and str(o.valid_from) > today:
            continue
        if o.valid_to and str(o.valid_to) < today:
            continue
        bonus = (flt(o.bonus_amount) if o.bonus_type == "Fixed Amount"
                 else amount * flt(o.bonus_percent) / 100.0)
        if bonus > best:
            best, best_offer = bonus, o.name
    return best, best_offer


def apply_recharge(customer, amount, ref_dt=None, ref_dn=None, remarks=None):
    """Credit Cash bucket + any Bonus bucket. Returns (cash_txn, bonus_txn|None,
    bonus_amount)."""
    cash_txn = credit(customer, amount, "Recharge", "Cash",
                      ref_dt, ref_dn, remarks)
    bonus, offer = get_applicable_bonus(amount)
    bonus_txn = None
    if bonus > 0:
        bonus_txn = credit(customer, bonus, "Bonus", "Bonus", ref_dt, ref_dn,
                           _("Recharge offer: {0}").format(offer))
    return cash_txn, bonus_txn, bonus


# --------------------------------------------------------------------------
# Staff / offline helpers
# --------------------------------------------------------------------------

@frappe.whitelist()
def offline_recharge(customer, amount, remarks=None):
    """Front-desk recharge. Section 269ST: never accept >= INR 2,00,000 cash
    from one person — keep offline loads on UPI."""
    frappe.only_for(("System Manager", "Cafe Manager"))
    amount = flt(amount)
    s = frappe.get_cached_doc("Duckies Settings")
    if amount < flt(s.min_recharge_amount):
        frappe.throw(_("Minimum recharge is {0}.").format(s.min_recharge_amount))
    if amount >= 200000:
        frappe.throw(_("Single cash receipts of Rs 2,00,000 or more are barred "
                       "under Section 269ST. Please split or use a bank/UPI "
                       "transfer recorded separately."))

    req = frappe.get_doc({
        "doctype": "Recharge Request", "customer": customer,
        "amount": amount, "status": "Pending", "channel": "Offline",
    }).insert(ignore_permissions=True)

    from duckies.payments.razorpay import settle_recharge_request
    settle_recharge_request(req.name, payment_id=None, remarks=remarks)
    req.reload()
    cash, bonus = get_buckets(customer)
    return {"recharge_request": req.name, "bonus": req.bonus_amount,
            "cash_balance": cash, "bonus_balance": bonus,
            "balance": cash + bonus}


@frappe.whitelist()
def manual_adjustment(customer, amount, direction, bucket, remarks):
    frappe.only_for("System Manager")
    if not (remarks or "").strip():
        frappe.throw(_("A reason is mandatory for manual adjustments."))
    if direction == "Credit":
        credit(customer, amount, "Adjustment", bucket, remarks=remarks)
    else:
        debit(customer, amount, "Adjustment", remarks=remarks)
    cash, bonus = get_buckets(customer)
    return {"cash_balance": cash, "bonus_balance": bonus,
            "balance": cash + bonus}
