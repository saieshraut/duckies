# Copyright (c) 2026, Duckie's Sports Cafe
"""Core wallet ledger — bucketed (Cash + Bonus).

Compliance model (RBI closed-system PPI + CBIC voucher circulars):
  * Cash bucket  = real money the customer loaded. Refundable to source.
  * Bonus bucket = promotional credit. NON-refundable, expires with wallet.
  * Spends consume Cash first, then Bonus (business policy). Remaining bonus
    is forfeited on any cash-out-to-source refund (see forfeit_bonus, called
    from payments.razorpay.process_refund), so a refund can never leave the
    customer holding both their money back AND live promotional credit.
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

QR_CODE_PREFIX = "DUCKIES-CUST:"


def qr_code_for_customer(customer: str) -> str:
    """Payload encoded in the customer's wallet QR (shown in the app, scanned
    by staff at the counter to pull up the customer's name/balance)."""
    return f"{QR_CODE_PREFIX}{customer}"


def get_customer_for_user(user: str | None = None) -> str:
    user = user or frappe.session.user
    if not user or user == "Guest":
        frappe.throw(_("Please log in first."), frappe.AuthenticationError)
    if frappe.db.get_value("User", user, "user_type") == "System User":
        frappe.throw(_("System users cannot access the cafe customer app."),
                     frappe.PermissionError)
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


def debit(customer, amount, txn_type, ref_dt=None, ref_dn=None, remarks=None,
          bucket=None):
    """Debit the wallet. May write two ledger rows (one per bucket touched).
    Returns the list of txns.

    ``bucket=None`` (default, used by all spend/refund paths): spend across
    buckets, Cash first then Bonus.

    NOTE on ordering: Cash-first means the customer's real money is consumed
    before promotional bonus. This is the business's chosen policy. Because a
    refund only ever returns the *remaining* Cash bucket (bonus is never
    refundable), payments.razorpay.process_refund forfeits any remaining
    Bonus via forfeit_bonus() in the same step — so the customer can never
    both cash out and keep live bonus. That guard keeps refunds safe under
    cash-first.

    ``bucket="Cash"`` or ``"Bonus"``: debit ONLY that bucket (fails if it
    alone doesn't cover the amount, even if the other bucket would). Used by
    manual_adjustment, where a System Manager explicitly picks which bucket
    to correct."""
    amount = flt(amount)
    if amount <= 0:
        frappe.throw(_("Debit amount must be positive."))
    if bucket is not None and bucket not in ("Cash", "Bonus"):
        frappe.throw(_("Invalid wallet bucket."))
    lock_customer(customer)
    cash, bonus = get_buckets(customer)

    if bucket == "Cash":
        available = cash
    elif bucket == "Bonus":
        available = bonus
    else:
        available = cash + bonus
    if amount > available + 0.005:  # paise tolerance
        frappe.throw(
            _("Insufficient {0}balance. Available: {1}, required: {2}. "
              "Please recharge your wallet.").format(
                (_(bucket) + " ") if bucket else "",
                frappe.format_value(available, {"fieldtype": "Currency"}),
                frappe.format_value(amount, {"fieldtype": "Currency"}),
            ),
            title=_("Insufficient Balance"),
        )

    txns = []
    if bucket == "Bonus":
        from_cash, from_bonus = 0.0, amount
    elif bucket == "Cash":
        from_cash, from_bonus = amount, 0.0
    else:
        from_cash = min(cash, amount)
        from_bonus = amount - from_cash
    if from_cash > 0:
        cash -= from_cash
        txns.append(_write_txn(customer, from_cash, txn_type, "Debit", "Cash",
                               cash, bonus, ref_dt, ref_dn, remarks))
    if from_bonus > 0:
        bonus -= from_bonus
        txns.append(_write_txn(customer, from_bonus, txn_type, "Debit", "Bonus",
                               cash, bonus, ref_dt, ref_dn, remarks))
    _persist(customer, cash, bonus)
    _touch_activity(customer)
    return txns


def forfeit_bonus(customer, ref_dt=None, ref_dn=None, remarks=None):
    """Zero out the Bonus bucket. MUST be called whenever Cash is refunded to
    an external source (request_refund/process_refund) — a refund-to-source
    physically hands real money back, and the customer can never be allowed
    to also walk away with live promotional credit funded by that same
    recharge. No-op (returns None) if there is no bonus to forfeit.

    Deliberately bypasses debit()'s cash-first ordering: this always empties
    Bonus specifically, regardless of the Cash balance."""
    lock_customer(customer)
    cash, bonus = get_buckets(customer)
    if bonus <= 0:
        return None
    txn = _write_txn(customer, bonus, "Forfeiture", "Debit", "Bonus",
                     cash, 0.0, ref_dt, ref_dn, remarks)
    _persist(customer, cash, 0.0)
    _touch_activity(customer)
    return txn


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
                "valid_from", "valid_to"],
        # Deterministic row order so a tie between two equally-good offers
        # always resolves to the same one, regardless of DB storage order.
        order_by="name asc")
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


def compute_offer_bonus(offer_name: str, amount: float) -> float:
    """Bonus for a specific named offer at this amount, honouring its min and
    validity. Returns 0 if the offer doesn't qualify."""
    amount = flt(amount)
    o = frappe.db.get_value(
        "Recharge Offer", offer_name,
        ["is_active", "min_recharge_amount", "bonus_type", "bonus_amount",
         "bonus_percent", "valid_from", "valid_to"], as_dict=True)
    if not o or not o.is_active:
        return 0.0
    if amount < flt(o.min_recharge_amount):
        return 0.0
    today = frappe.utils.today()
    if o.valid_from and str(o.valid_from) > today:
        return 0.0
    if o.valid_to and str(o.valid_to) < today:
        return 0.0
    return (flt(o.bonus_amount) if o.bonus_type == "Fixed Amount"
            else amount * flt(o.bonus_percent) / 100.0)


def resolve_offer(offer, amount):
    """Given the caller's offer choice, return (bonus_amount, offer_label).

    offer = None      -> auto: pick the best matching active offer
    offer = "none"    -> suppress: no bonus (manager override)
    offer = "<name>"  -> use that specific offer (0 bonus if it doesn't qualify)
    """
    if offer is None:
        return get_applicable_bonus(amount)
    if str(offer).lower() == "none":
        return 0.0, None
    return compute_offer_bonus(offer, amount), offer


def apply_recharge(customer, amount, ref_dt=None, ref_dn=None, remarks=None,
                   deposit_account=None, offer=None):
    """Credit Cash bucket + any Bonus bucket, AND post the accounting Journal
    Entry. This is the single recharge entry point — every path (Razorpay
    webhook, offline front-desk, direct call) goes through here, so the books
    are always in sync with the wallet ledger.

    ``deposit_account`` overrides the default deposit account (e.g. front-desk
    Cash-in-hand vs bank vs UPI settlement). Falls back to Duckies Settings.

    ``offer`` controls the bonus: None = auto-pick best matching offer;
    "none" = no bonus (override); an offer name = use that specific offer.

    Returns (cash_txn, bonus_txn|None, bonus_amount, journal_entry_name)."""
    cash_txn = credit(customer, amount, "Recharge", "Cash",
                      ref_dt, ref_dn, remarks)
    bonus, offer_label = resolve_offer(offer, amount)
    bonus_txn = None
    if bonus > 0:
        bonus_txn = credit(customer, bonus, "Bonus", "Bonus", ref_dt, ref_dn,
                           _("Recharge offer: {0}").format(offer_label))

    # Accounting: Dr Bank/Razorpay + Dr Promo Expense / Cr Wallet Liability.
    je_name = post_recharge_accounting(customer, flt(amount), flt(bonus),
                                       ref_dt, ref_dn, deposit_account)
    return cash_txn, bonus_txn, bonus, je_name


def post_recharge_accounting(customer, amount, bonus, ref_dt=None, ref_dn=None,
                             deposit_account=None):
    """Dr Bank/Razorpay (cash) + Dr Promo Expense (bonus) / Cr Wallet
    Liability. Non-fatal: a misconfigured account is logged, never blocks the
    customer's wallet credit — accounts can repost from the Error Log.

    Returns the Journal Entry name, or None if skipped/failed."""
    s = frappe.get_cached_doc("Duckies Settings")
    ref = f"{ref_dt} {ref_dn}".strip() if ref_dt else customer
    deposit = deposit_account or s.deposit_account

    if not (s.company and s.wallet_liability_account and deposit):
        frappe.log_error(
            title=f"Recharge accounting skipped ({customer})",
            message="Set company / wallet_liability_account / deposit_account "
                    "in Duckies Settings, then post the JE manually.")
        return None
    try:
        accounts = [
            {"account": deposit,
             "debit_in_account_currency": flt(amount)},
            {"account": s.wallet_liability_account,
             "credit_in_account_currency": flt(amount)},
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
            "user_remark": _("Wallet recharge for {0} (ref: {1})").format(
                customer, ref),
            "accounts": accounts,
        })
        je.flags.ignore_permissions = True
        je.insert()
        je.submit()
        return je.name
    except Exception:
        frappe.log_error(title=f"Recharge JE failed ({customer})",
                         message=frappe.get_traceback())
        return None


# --------------------------------------------------------------------------
# Staff / offline helpers
# --------------------------------------------------------------------------

@frappe.whitelist(methods=["POST"])
def offline_recharge(customer, amount, payment_mode="Cash", remarks=None,
                     payment_account=None, payment_reference=None):
    """Front-desk recharge. Creates + submits an Offline Recharge Request,
    which loads the wallet and posts accounting via its on_submit. Staff can
    also do this straight from the Recharge Request form in the desk."""
    frappe.only_for(("System Manager", "Cafe Manager"))
    req = frappe.get_doc({
        "doctype": "Recharge Request",
        "customer": customer,
        "amount": flt(amount),
        "channel": "Offline",
        "payment_mode": payment_mode,
        "payment_account": payment_account,
        "payment_reference": payment_reference,
        "status": "Pending",
    })
    req.flags.ignore_permissions = True
    req.insert()
    req.submit()  # on_submit -> wallet credit + accounting
    req.reload()
    cash, bonus = get_buckets(customer)
    return {"recharge_request": req.name, "bonus": req.bonus_amount,
            "cash_balance": cash, "bonus_balance": bonus,
            "balance": cash + bonus}


@frappe.whitelist(methods=["POST"])
def staff_lookup_customer(code):
    """Resolve a scanned wallet QR (or a bare Customer ID typed/scanned in)
    to the customer's identity + balance. Used by the desk "Scan Customer"
    page — camera scan or a keyboard-wedge handheld scanner both land here."""
    frappe.only_for(("System Manager", "Cafe Manager"))
    code = (code or "").strip()
    if code.startswith(QR_CODE_PREFIX):
        code = code[len(QR_CODE_PREFIX):]
    if not code:
        frappe.throw(_("Empty code."))

    c = frappe.db.get_value(
        "Customer", code,
        ["name", "customer_name", "mobile_no", "email_id",
         "custom_wallet_balance", "custom_wallet_cash", "custom_wallet_bonus"],
        as_dict=True)
    if not c:
        frappe.throw(_("No customer found for this QR code."))

    return {
        "customer": c.name,
        "name": c.customer_name,
        "mobile": c.mobile_no,
        "email": c.email_id,
        "wallet_balance": flt(c.custom_wallet_balance),
        "cash_balance": flt(c.custom_wallet_cash),
        "bonus_balance": flt(c.custom_wallet_bonus),
    }


@frappe.whitelist(methods=["POST"])
def manual_adjustment(customer, amount, direction, bucket, remarks):
    """``bucket`` ("Cash" or "Bonus") is honoured for BOTH directions: a
    Credit adds to that bucket, and a Debit is taken from that bucket only
    (not cash-first) — so a System Manager correcting an over-credited Bonus
    row, say, can be sure the correction actually lands on Bonus."""
    frappe.only_for("System Manager")
    if not (remarks or "").strip():
        frappe.throw(_("A reason is mandatory for manual adjustments."))
    if direction == "Credit":
        credit(customer, amount, "Adjustment", bucket, remarks=remarks)
    else:
        debit(customer, amount, "Adjustment", remarks=remarks, bucket=bucket)
    cash, bonus = get_buckets(customer)
    return {"cash_balance": cash, "bonus_balance": bonus,
            "balance": cash + bonus}
