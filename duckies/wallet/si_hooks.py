# Copyright (c) 2026, Duckie's Sports Cafe
"""Sales Invoice integration — the single spending path.

Every purchase (food, drinks, event seats, game time) is a normal Sales
Invoice. On submit we debit the wallet ledger for the grand total and settle
the invoice with a Payment Entry through the Wallet account; on cancel we
refund the wallet to the original buckets.

We deliberately do NOT use is_pos=1 for programmatic invoices: POS invoices
require a POS Profile, default warehouse and write-off accounts, which makes
them fragile to create from API/booking code. A normal invoice + Payment
Entry is predictable in web requests and in `bench execute` alike.

The interactive ERPNext POS screen (for the bar counter) still works and is
governed by validate_wallet_payment below, which blocks non-Wallet tenders.
"""

import frappe
from frappe import _
from frappe.utils import flt

from duckies.wallet.api import (
    credit, debit, get_balance, has_txn_for_reference, lock_customer,
)

WALLET_MODE = "Wallet"


def _is_wallet_customer(customer) -> bool:
    """A customer linked to a portal user (i.e. a wallet holder)."""
    if not customer:
        return False
    return bool(frappe.db.get_value("Customer", customer, "custom_user")) or \
        frappe.db.exists("Wallet Transaction", {"customer": customer})


def _pos_wallet_amount(doc) -> float:
    return sum(
        flt(p.amount) for p in (doc.get("payments") or [])
        if p.mode_of_payment == WALLET_MODE
    )


# --------------------------------------------------------------------------
# validate — guards the interactive POS screen (no cash/card at the counter)
# --------------------------------------------------------------------------

def validate_wallet_payment(doc, method=None):
    settings = frappe.get_cached_doc("Duckies Settings")

    if doc.is_pos and settings.enforce_wallet_only:
        for p in (doc.get("payments") or []):
            if flt(p.amount) and p.mode_of_payment != WALLET_MODE:
                frappe.throw(
                    _("Only Wallet payments are accepted at Duckie's. "
                      "Remove the '{0}' payment row.").format(p.mode_of_payment),
                    title=_("Wallet Only"),
                )

    # Advisory balance check for a wallet customer (authoritative check is the
    # locked debit on submit).
    amt = doc.grand_total if _is_wallet_customer(doc.customer) else _pos_wallet_amount(doc)
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


# --------------------------------------------------------------------------
# on_submit — debit the ledger for wallet customers
# --------------------------------------------------------------------------

def debit_wallet_on_submit(doc, method=None):
    """Debit the wallet ledger when a wallet customer's invoice is submitted.
    Idempotent via has_txn_for_reference, so it fires exactly once whether the
    invoice came from make_wallet_invoice or the interactive POS screen."""
    amt = doc.grand_total if _is_wallet_customer(doc.customer) else _pos_wallet_amount(doc)
    if not amt:
        return
    if has_txn_for_reference(doc.customer, "Debit", "Sales Invoice", doc.name):
        return  # idempotent
    debit(
        doc.customer, amt, "Spend",
        "Sales Invoice", doc.name,
        remarks=_("Invoice {0}").format(doc.name),
    )


def refund_wallet_on_cancel(doc, method=None):
    """Return money to the same buckets it came from, so a cancelled
    bonus-funded booking refunds bonus (not cash)."""
    if not has_txn_for_reference(doc.customer, "Debit", "Sales Invoice", doc.name):
        return

    # Idempotency: has a refund for THIS invoice already been posted? We can't
    # link the Refund txn to the invoice (it's mid-cancel -> CancelledLinkError),
    # so we tag the invoice name in remarks and check that instead.
    refund_tag = f"[refund:{doc.name}]"
    if frappe.db.exists("Wallet Transaction", {
        "customer": doc.customer, "direction": "Credit", "docstatus": 1,
        "transaction_type": "Refund", "remarks": ("like", f"%{refund_tag}%")}):
        return  # already refunded

    rows = frappe.get_all(
        "Wallet Transaction",
        filters={"customer": doc.customer, "direction": "Debit", "docstatus": 1,
                 "reference_doctype": "Sales Invoice", "reference_name": doc.name},
        fields=["bucket", "amount"])
    per_bucket = {"Cash": 0.0, "Bonus": 0.0}
    for r in rows:
        per_bucket[r.bucket] = per_bucket.get(r.bucket, 0.0) + flt(r.amount)

    for bucket, bamt in per_bucket.items():
        if bamt > 0:
            # Reference the Customer (always valid); the invoice is in remarks.
            credit(
                doc.customer, bamt, "Refund", bucket,
                "Customer", doc.customer,
                remarks=_("Refund for cancelled invoice {0} {1}").format(
                    doc.name, refund_tag),
            )


# --------------------------------------------------------------------------
# Helper used by event bookings and online food orders
# --------------------------------------------------------------------------

def make_wallet_invoice(customer, items, remarks=None):
    """Create + submit a normal Sales Invoice fully paid from the wallet.

    ``items``: [{"item_code": ..., "qty": ..., "rate": ...}, ...]
    Debits the wallet ledger (bonus-first) and settles the invoice with a
    Payment Entry through the Wallet account. All in one DB transaction, so a
    failed debit rolls the invoice back too.
    """
    lock_customer(customer)  # hold the lock across pricing + debit

    settings = frappe.get_cached_doc("Duckies Settings")
    company = settings.company or frappe.defaults.get_user_default("Company")
    if not company:
        frappe.throw(_("Set the Company in Duckies Settings before taking "
                       "wallet payments."))

    si = frappe.get_doc({
        "doctype": "Sales Invoice",
        "customer": customer,
        "company": company,
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
    si.insert()
    si.submit()  # on_submit -> debit_wallet_on_submit debits the ledger

    # Settle the invoice via a Payment Entry through the Wallet account so the
    # customer ledger / liability account reconciles and the invoice shows Paid.
    _settle_via_wallet_account(si, company, settings)
    return si


def _settle_via_wallet_account(si, company, settings):
    """Create + submit a Payment Entry: Dr Wallet Liability / Cr Debtors,
    clearing the invoice. Non-fatal on failure (ledger already debited) but
    logged so accounts can repost."""
    wallet_account = settings.wallet_liability_account
    if not wallet_account:
        frappe.log_error(
            title=f"Wallet settlement skipped for {si.name}",
            message="Set wallet_liability_account in Duckies Settings.")
        return
    try:
        from erpnext.accounts.doctype.payment_entry.payment_entry import (
            get_payment_entry,
        )
        pe = get_payment_entry("Sales Invoice", si.name,
                               party_amount=si.grand_total,
                               bank_account=wallet_account)
        pe.reference_no = si.name
        pe.reference_date = si.posting_date
        pe.flags.ignore_permissions = True
        pe.insert()
        pe.submit()
    except Exception:
        frappe.log_error(title=f"Wallet Payment Entry failed for {si.name}",
                         message=frappe.get_traceback())