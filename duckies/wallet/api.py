# Copyright (c) 2026, Duckie's Sports Cafe
"""Core wallet ledger.

Every rupee that enters or leaves a customer's wallet MUST pass through
``create_wallet_txn``. It takes a row-level lock on the Customer, so two
simultaneous spends (e.g. bar POS + web booking) can never both pass the
balance check.
"""

import frappe
from frappe import _
from frappe.utils import flt


def get_customer_for_user(user: str | None = None) -> str:
    """Resolve the Customer linked to a portal login."""
    user = user or frappe.session.user
    if not user or user == "Guest":
        frappe.throw(_("Please log in first."), frappe.AuthenticationError)
    customer = frappe.db.get_value("Customer", {"custom_user": user}, "name")
    if not customer:
        frappe.throw(_("No customer profile is linked to this account. "
                       "Please contact the cafe front desk."))
    return customer


def get_balance(customer: str) -> float:
    return flt(frappe.db.get_value("Customer", customer, "custom_wallet_balance"))


def lock_customer(customer: str) -> None:
    """Row-level lock; held until the current transaction commits/rolls back."""
    frappe.db.sql(
        "SELECT name FROM `tabCustomer` WHERE name = %s FOR UPDATE", (customer,)
    )


def create_wallet_txn(
    customer: str,
    amount: float,
    transaction_type: str,
    direction: str,
    reference_doctype: str | None = None,
    reference_name: str | None = None,
    remarks: str | None = None,
):
    """Append one immutable row to the wallet ledger and update the cached
    balance. Raises on insufficient balance for debits."""
    amount = flt(amount)
    if amount <= 0:
        frappe.throw(_("Wallet transaction amount must be positive."))
    if direction not in ("Credit", "Debit"):
        frappe.throw(_("Invalid wallet direction."))

    lock_customer(customer)
    balance = get_balance(customer)

    if direction == "Debit" and amount > balance + 0.005:  # paise tolerance
        frappe.throw(
            _("Insufficient wallet balance. Available: {0}, required: {1}. "
              "Please recharge your wallet.").format(
                frappe.format_value(balance, {"fieldtype": "Currency"}),
                frappe.format_value(amount, {"fieldtype": "Currency"}),
            ),
            title=_("Insufficient Balance"),
        )

    new_balance = balance + amount if direction == "Credit" else balance - amount

    txn = frappe.get_doc({
        "doctype": "Wallet Transaction",
        "customer": customer,
        "transaction_type": transaction_type,
        "direction": direction,
        "amount": amount,
        "balance_after": new_balance,
        "reference_doctype": reference_doctype,
        "reference_name": reference_name,
        "remarks": remarks,
    })
    txn.flags.ignore_permissions = True
    txn.insert()
    txn.submit()

    frappe.db.set_value(
        "Customer", customer, "custom_wallet_balance", new_balance,
        update_modified=False,
    )
    return txn


def has_txn_for_reference(customer, direction, ref_dt, ref_dn) -> bool:
    """Idempotency guard: has this reference already produced a ledger row?"""
    return bool(frappe.db.exists("Wallet Transaction", {
        "customer": customer, "direction": direction, "docstatus": 1,
        "reference_doctype": ref_dt, "reference_name": ref_dn,
    }))


# --------------------------------------------------------------------------
# Recharge offers
# --------------------------------------------------------------------------

def get_applicable_bonus(amount: float) -> tuple[float, str | None]:
    """Return (bonus_amount, offer_name) for the best active offer, or (0, None)."""
    amount = flt(amount)
    today = frappe.utils.today()
    offers = frappe.get_all(
        "Recharge Offer",
        filters={"is_active": 1, "min_recharge_amount": ("<=", amount)},
        fields=["name", "bonus_type", "bonus_amount", "bonus_percent",
                "valid_from", "valid_to"],
    )
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


def apply_recharge(
    customer: str,
    amount: float,
    reference_doctype: str | None = None,
    reference_name: str | None = None,
    remarks: str | None = None,
):
    """Credit a recharge plus any applicable bonus. Returns (recharge_txn,
    bonus_txn_or_None, bonus_amount)."""
    txn = create_wallet_txn(
        customer, amount, "Recharge", "Credit",
        reference_doctype, reference_name, remarks,
    )
    bonus, offer = get_applicable_bonus(amount)
    bonus_txn = None
    if bonus > 0:
        bonus_txn = create_wallet_txn(
            customer, bonus, "Bonus", "Credit",
            reference_doctype, reference_name,
            _("Recharge offer: {0}").format(offer),
        )
    return txn, bonus_txn, bonus


# --------------------------------------------------------------------------
# Admin helpers (front-desk / offline flows)
# --------------------------------------------------------------------------

@frappe.whitelist()
def offline_recharge(customer: str, amount: float, remarks: str | None = None):
    """Front-desk recharge (e.g. customer paid via the cafe's UPI QR).
    Restricted to staff roles; also posts the accounting Journal Entry."""
    frappe.only_for(("System Manager", "Cafe Manager"))
    amount = flt(amount)
    settings = frappe.get_cached_doc("Duckies Settings")
    if amount < flt(settings.min_recharge_amount):
        frappe.throw(_("Minimum recharge is {0}.").format(settings.min_recharge_amount))

    req = frappe.get_doc({
        "doctype": "Recharge Request", "customer": customer,
        "amount": amount, "status": "Pending", "channel": "Offline",
    }).insert(ignore_permissions=True)

    from duckies.payments.razorpay import settle_recharge_request
    settle_recharge_request(req.name, payment_id=None, remarks=remarks)
    req.reload()
    return {"recharge_request": req.name, "bonus": req.bonus_amount,
            "balance": get_balance(customer)}


@frappe.whitelist()
def manual_adjustment(customer: str, amount: float, direction: str,
                      remarks: str):
    """Staff-only correction entry. Always demands a reason."""
    frappe.only_for("System Manager")
    if not (remarks or "").strip():
        frappe.throw(_("A reason is mandatory for manual adjustments."))
    txn = create_wallet_txn(customer, amount, "Adjustment", direction,
                            remarks=remarks)
    return {"wallet_transaction": txn.name, "balance": get_balance(customer)}
