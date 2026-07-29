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
                "custom_wallet_balance", "custom_wallet_last_activity",
                "custom_wallet_reminders_sent"])


# --------------------------------------------------------------------------
# Reminders (daily)
# --------------------------------------------------------------------------

def _parse_sent_reminders(raw: str | None, cycle_key: str) -> set:
    """``raw`` is '<expiry_date>|<days,...>'. Returns the set of thresholds
    already notified for THIS expiry cycle — an empty set if the wallet's
    expiry date has moved on (recharge/spend reset the clock) since the last
    reminder was sent, since that's a new cycle."""
    if not raw or "|" not in raw:
        return set()
    stored_cycle, days_csv = raw.split("|", 1)
    if stored_cycle != cycle_key:
        return set()
    return {int(d) for d in days_csv.split(",") if d.strip().lstrip("-").isdigit()}


def _save_sent_reminders(customer: str, cycle_key: str, days_sent: set) -> None:
    value = f"{cycle_key}|{','.join(str(d) for d in sorted(days_sent, reverse=True))}"
    frappe.db.set_value("Customer", customer, "custom_wallet_reminders_sent",
                        value, update_modified=False)


def send_expiry_reminders():
    """Send the most urgent not-yet-sent reminder threshold per customer.

    Uses ``days_left <= threshold`` (a catch-up check) rather than an exact
    match, so a scheduler outage that skips the exact day a threshold falls
    on doesn't silently lose that customer's reminder — it just fires on the
    next run instead. ``custom_wallet_reminders_sent`` tracks which
    thresholds have already fired for the wallet's CURRENT expiry date, so
    the same threshold is never re-sent, and each recharge/spend (which
    pushes expiry out and starts a new cycle) naturally resets it."""
    raw = (_settings().expiry_reminder_days or "30,7")
    try:
        days_list = sorted({int(x) for x in str(raw).split(",") if x.strip()},
                           reverse=True)
    except ValueError:
        days_list = [30, 7]

    t = getdate(today())
    for c in _wallets_with_balance():
        last = c.custom_wallet_last_activity
        if not last:
            continue
        exp = expiry_date_for(last)
        days_left = (exp - t).days
        if days_left < 0:
            continue  # already lapsed — expire_lapsed_wallets handles it

        cycle_key = str(exp)
        sent = _parse_sent_reminders(c.custom_wallet_reminders_sent, cycle_key)

        due = [d for d in days_list if days_left <= d and d not in sent]
        if not due:
            continue

        # The smallest due threshold is the most urgent (closest to expiry);
        # if we're catching up after a missed run, that's the one worth
        # emailing about — the message always states the true expiry date.
        threshold = min(due)
        _send_reminder(c, exp, days_left)
        # Every threshold at or above the one we just sent is now moot for
        # this cycle (a 7-day reminder supersedes an unsent 30-day one).
        sent |= {d for d in days_list if d >= threshold}
        _save_sent_reminders(c.name, cycle_key, sent)


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
