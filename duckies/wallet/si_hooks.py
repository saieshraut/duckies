# Copyright (c) 2026, Duckie's Sports Cafe
"""Sales Invoice integration.

The single spending path: every purchase (food, drinks, event seats, game
time) becomes a Sales Invoice paid with Mode of Payment "Wallet". The
on_submit hook debits the ledger; on_cancel refunds it. Because this is the
only configured mode of payment, "no cash, no cards" is enforced by the
system, not by staff discipline.
"""

import frappe
from frappe import _
from frappe.utils import flt

from duckies.wallet.api import (
    create_wallet_txn, get_balance, has_txn_for_reference, lock_customer,
)

WALLET_MODE = "Wallet"


def _wallet_amount(doc) -> float:
    return sum(
        flt(p.amount) for p in (doc.get("payments") or [])
        if p.mode_of_payment == WALLET_MODE
    )


def validate_wallet_payment(doc, method=None):
    """Runs on Sales Invoice validate."""
    settings = frappe.get_cached_doc("Duckies Settings")

    if doc.is_pos and settings.enforce_wallet_only:
        for p in (doc.get("payments") or []):
            if flt(p.amount) and p.mode_of_payment != WALLET_MODE:
                frappe.throw(
                    _("Only Wallet payments are accepted at Duckie's. "
                      "Remove the '{0}' payment row.").format(p.mode_of_payment),
                    title=_("Wallet Only"),
                )

    # Early, advisory balance check (final authoritative check happens under
    # lock in debit_wallet_on_submit).
    amt = _wallet_amount(doc)
    if amt and doc.customer and amt > get_balance(doc.customer) + 0.005:
        frappe.throw(
            _("{0} has insufficient wallet balance ({1}) for this bill ({2}). "
              "Please recharge first.").format(
                doc.customer_name or doc.customer,
                frappe.format_value(get_balance(doc.customer),
                                    {"fieldtype": "Currency"}),
                frappe.format_value(amt, {"fieldtype": "Currency"}),
            ),
            title=_("Insufficient Balance"),
        )


def debit_wallet_on_submit(doc, method=None):
    amt = _wallet_amount(doc)
    if not amt:
        return
    if has_txn_for_reference(doc.customer, "Debit", "Sales Invoice", doc.name):
        return  # idempotent
    create_wallet_txn(
        doc.customer, amt, "Spend", "Debit",
        "Sales Invoice", doc.name,
        remarks=_("Invoice {0}").format(doc.name),
    )


def refund_wallet_on_cancel(doc, method=None):
    amt = _wallet_amount(doc)
    if not amt:
        return
    if not has_txn_for_reference(doc.customer, "Debit", "Sales Invoice", doc.name):
        return  # was never debited
    if has_txn_for_reference(doc.customer, "Credit", "Sales Invoice", doc.name):
        return  # already refunded
    create_wallet_txn(
        doc.customer, amt, "Refund", "Credit",
        "Sales Invoice", doc.name,
        remarks=_("Refund for cancelled invoice {0}").format(doc.name),
    )


# --------------------------------------------------------------------------
# Helper used by event bookings and online food orders
# --------------------------------------------------------------------------

def make_wallet_invoice(customer: str, items: list[dict], remarks: str | None = None):
    """Create + submit a POS Sales Invoice fully paid from the wallet.

    ``items``: [{"item_code": ..., "qty": ..., "rate": ...}, ...]
    The submit hook performs the actual wallet debit; everything runs in one
    DB transaction, so a failed debit rolls the invoice back too.
    """
    lock_customer(customer)  # hold the lock across pricing + debit

    si = frappe.get_doc({
        "doctype": "Sales Invoice",
        "customer": customer,
        "is_pos": 1,
        "update_stock": 0,
        "remarks": remarks,
        "items": [
            {
                "item_code": it["item_code"],
                "qty": flt(it.get("qty") or 1),
                "rate": flt(it["rate"]) if it.get("rate") is not None else None,
            }
            for it in items
        ],
    })
    si.flags.ignore_permissions = True
    si.set_missing_values()
    si.calculate_taxes_and_totals()
    si.append("payments", {
        "mode_of_payment": WALLET_MODE,
        "amount": si.grand_total,
    })
    si.insert()
    si.submit()
    return si
