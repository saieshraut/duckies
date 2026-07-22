# Copyright (c) 2026, Duckie's Sports Cafe
"""Wallet expiry & breakage.

Game-zone convention: a wallet expires N months after its LAST activity
(each recharge or spend resets the clock — more defensible under the
Consumer Protection Act than expiry-from-load-date). We send reminders
before expiry, then write the lapsed balance back to income.

CBIC Circular 243/37/2024: breakage (unredeemed balance) is NOT a supply,
so no GST — it's ordinary income for income-tax only.
"""

import frappe
from frappe import _
from frappe.utils import (
    add_months, add_to_date, flt, get_datetime, getdate, now_datetime, today,
)


def _settings():
    return frappe.get_cached_doc("Duckies Settings")


def _validity_months() -> int:
    return int(_settings().wallet_validity_months or 12)


def expiry_date_for(last_activity) -> "date":
    return getdate(add_months(get_datetime(last_activity), _validity_months()))


def _wallets_with_balance():
    return frappe.get_all(
        "Customer",
        filters={"custom_wallet_balance": (">", 0)},
        fields=["name", "customer_name", "email_id",
                "custom_wallet_cash", "custom_wallet_bonus",
                "custom_wallet_balance", "custom_wallet_last_activity"])


# --------------------------------------------------------------------------
# Reminders (daily)
# --------------------------------------------------------------------------

def send_expiry_reminders():
    raw = (_settings().expiry_reminder_days or "30,7")
    try:
        days_list = sorted({int(x) for x in str(raw).split(",") if x.strip()})
    except ValueError:
        days_list = [30, 7]

    t = getdate(today())
    for c in _wallets_with_balance():
        last = c.custom_wallet_last_activity
        if not last:
            continue
        exp = expiry_date_for(last)
        days_left = (exp - t).days
        if days_left in days_list:
            _send_reminder(c, exp, days_left)


def _send_reminder(customer_row, exp_date, days_left):
    if not customer_row.email_id:
        return
    try:
        frappe.sendmail(
            recipients=[customer_row.email_id],
            subject=_("Your Duckie's wallet balance expires in {0} days")
                    .format(days_left),
            message=_(
                "Hi {name},<br><br>Your Duckie's wallet balance of "
                "<b>{bal}</b> will expire on <b>{exp}</b> if the wallet stays "
                "inactive. Pop in for a game, a coffee or a cocktail before "
                "then to keep it active!<br><br>See you at Duckie's."
            ).format(
                name=customer_row.customer_name,
                bal=frappe.format_value(customer_row.custom_wallet_balance,
                                        {"fieldtype": "Currency"}),
                exp=frappe.format(exp_date, {"fieldtype": "Date"}),
            ),
            reference_doctype="Customer", reference_name=customer_row.name,
        )
    except Exception:
        frappe.log_error(title=f"Expiry reminder failed: {customer_row.name}",
                         message=frappe.get_traceback())


# --------------------------------------------------------------------------
# Expiry / breakage write-back (daily)
# --------------------------------------------------------------------------

def expire_lapsed_wallets():
    from duckies.wallet.api import debit, lock_customer

    s = _settings()
    t = getdate(today())
    for c in _wallets_with_balance():
        last = c.custom_wallet_last_activity
        if not last or expiry_date_for(last) > t:
            continue

        lock_customer(c.name)
        # re-read under lock
        bal = flt(frappe.db.get_value("Customer", c.name,
                                      "custom_wallet_balance"))
        if bal <= 0:
            continue

        # Debit the whole balance as Expiry (bonus first, then cash — order
        # doesn't matter here since everything goes to breakage income).
        debit(c.name, bal, "Expiry", "Customer", c.name,
              remarks=_("Wallet expired after {0} months of inactivity")
                      .format(_validity_months()))
        _post_breakage(c.name, bal, s)

    frappe.db.commit()


def _post_breakage(customer, amount, s):
    """Dr Wallet Liability / Cr Breakage Income. No GST (CBIC 243/37/2024)."""
    if not (s.company and s.wallet_liability_account and s.breakage_income_account):
        frappe.log_error(
            title=f"Breakage accounting skipped: {customer}",
            message="Set breakage_income_account in Duckies Settings.")
        return
    try:
        je = frappe.get_doc({
            "doctype": "Journal Entry", "company": s.company,
            "posting_date": today(),
            "user_remark": f"Wallet breakage (expiry) for {customer}",
            "accounts": [
                {"account": s.wallet_liability_account,
                 "debit_in_account_currency": flt(amount)},
                {"account": s.breakage_income_account,
                 "credit_in_account_currency": flt(amount)},
            ],
        })
        je.flags.ignore_permissions = True
        je.insert()
        je.submit()
    except Exception:
        frappe.log_error(title=f"Breakage JE failed: {customer}",
                         message=frappe.get_traceback())
