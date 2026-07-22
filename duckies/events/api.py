# Copyright (c) 2026, Duckie's Sports Cafe
"""Event booking & cancellation. All money movement goes through the Sales
Invoice path (see wallet/si_hooks.py), so bookings and food orders share one
audited debit/refund mechanism."""

import frappe
from frappe import _
from frappe.utils import cint, flt, get_datetime, now_datetime

from duckies.events.tasks import get_or_create_event_item
from duckies.wallet.si_hooks import make_wallet_invoice


def _lock_event(event_name: str):
    frappe.db.sql(
        "SELECT name FROM `tabCafe Event` WHERE name = %s FOR UPDATE",
        (event_name,),
    )


def book_event(customer: str, event: str, seats: int = 1):
    """Atomically: lock event → check capacity → invoice (wallet debit via
    hook) → bump seats → create booking. Any failure rolls everything back."""
    seats = cint(seats)
    if seats < 1:
        frappe.throw(_("Book at least one seat."))

    _lock_event(event)
    ev = frappe.get_doc("Cafe Event", event)

    if ev.status != "Upcoming":
        frappe.throw(_("This event is not open for booking (status: {0}).")
                     .format(_(ev.status)))
    if get_datetime(f"{ev.date} {ev.start_time}") < now_datetime():
        frappe.throw(_("This event has already started."))

    seats_left = cint(ev.capacity) - cint(ev.seats_booked)
    if seats > seats_left:
        frappe.throw(
            _("Only {0} seat(s) left for {1}.").format(seats_left, ev.event_name),
            title=_("Event Full") if seats_left == 0 else _("Not Enough Seats"),
        )

    if not ev.item:
        ev.item = get_or_create_event_item(ev.event_name)
        ev.db_set("item", ev.item, update_modified=False)

    si = make_wallet_invoice(
        customer,
        [{"item_code": ev.item, "qty": seats, "rate": flt(ev.price)}],
        remarks=_("Booking: {0} on {1}").format(ev.event_name, ev.date),
    )

    ev.db_set("seats_booked", cint(ev.seats_booked) + seats,
              update_modified=False)

    booking = frappe.get_doc({
        "doctype": "Event Booking",
        "customer": customer,
        "event": ev.name,
        "seats": seats,
        "amount_paid": si.grand_total,
        "status": "Confirmed",
        "booked_on": now_datetime(),
        "sales_invoice": si.name,
    }).insert(ignore_permissions=True)

    return booking


def cancel_booking(customer: str, booking_name: str):
    """Cancel a booking and refund the wallet.

    Design: we do NOT cancel the original Sales Invoice (cancelling a settled,
    GST-linked invoice fights a chain of ERPNext guards and is the wrong
    accounting model anyway). Instead we:
      1. post the wallet Refund directly, back to the same buckets the spend
         came from (bonus->bonus, cash->cash);
      2. raise a Credit Note (return invoice) so the books reverse cleanly and
         GST is handled the proper way;
      3. release the seats and mark the booking Cancelled.
    The original invoice stays on record, as it should.
    """
    booking = frappe.get_doc("Event Booking", booking_name)
    if booking.customer != customer:
        frappe.throw(_("This booking does not belong to you."),
                     frappe.PermissionError)
    if booking.status != "Confirmed":
        frappe.throw(_("Only confirmed bookings can be cancelled."))

    ev = frappe.get_doc("Cafe Event", booking.event)
    cutoff_hours = cint(
        frappe.get_cached_doc("Duckies Settings").cancellation_cutoff_hours
    )
    start = get_datetime(f"{ev.date} {ev.start_time}")
    hours_to_go = (start - now_datetime()).total_seconds() / 3600.0
    if hours_to_go < cutoff_hours:
        frappe.throw(
            _("Cancellations close {0} hours before the event starts.")
            .format(cutoff_hours),
            title=_("Too Late to Cancel"),
        )

    # 1. Refund the wallet to the original buckets (idempotent).
    _refund_booking_to_wallet(booking)

    # 2. Credit Note for the books (non-fatal; wallet refund already done).
    if booking.sales_invoice:
        _make_credit_note(booking.sales_invoice)

    # 3. Release seats and close the booking.
    _lock_event(ev.name)
    ev.db_set(
        "seats_booked",
        max(0, cint(ev.seats_booked) - cint(booking.seats)),
        update_modified=False,
    )
    booking.db_set("status", "Cancelled")
    return booking


def _refund_booking_to_wallet(booking):
    """Post Refund credits mirroring the original Spend debits for this
    booking's invoice. Idempotent via a [refund:<invoice>] remarks tag."""
    from duckies.wallet.api import credit

    invoice = booking.sales_invoice
    if not invoice:
        return

    refund_tag = f"[refund:{invoice}]"
    if frappe.db.exists("Wallet Transaction", {
        "customer": booking.customer, "direction": "Credit", "docstatus": 1,
        "transaction_type": "Refund", "remarks": ("like", f"%{refund_tag}%")}):
        return  # already refunded

    rows = frappe.get_all(
        "Wallet Transaction",
        filters={"customer": booking.customer, "direction": "Debit",
                 "docstatus": 1, "reference_doctype": "Sales Invoice",
                 "reference_name": invoice},
        fields=["bucket", "amount"])
    per_bucket = {"Cash": 0.0, "Bonus": 0.0}
    for r in rows:
        per_bucket[r.bucket] = per_bucket.get(r.bucket, 0.0) + flt(r.amount)

    for bucket, bamt in per_bucket.items():
        if bamt > 0:
            credit(
                booking.customer, bamt, "Refund", bucket,
                "Customer", booking.customer,
                remarks=_("Refund for cancelled booking (invoice {0}) {1}")
                        .format(invoice, refund_tag),
            )


def _make_credit_note(invoice_name):
    """Create + submit a return Sales Invoice (Credit Note) against the
    original, settled immediately through the Wallet account so it doesn't
    leave a dangling negative outstanding.

    Because the customer's money went back to their WALLET (not their bank),
    the return is paid via the Wallet mode of payment: this posts
    Dr Revenue-reversal / Cr Wallet Liability, i.e. the amount returns to
    "money we owe on wallets" — which is exactly where it now sits.

    Non-fatal: logged if it fails, since the wallet refund (the customer-facing
    part) has already succeeded."""
    try:
        si = frappe.get_doc("Sales Invoice", invoice_name)
        if si.docstatus != 1:
            return
        # Guard against a duplicate credit note for the same invoice.
        if frappe.db.exists("Sales Invoice",
                            {"return_against": invoice_name, "docstatus": 1}):
            return

        settings = frappe.get_cached_doc("Duckies Settings")
        cn = frappe.get_doc({
            "doctype": "Sales Invoice",
            "customer": si.customer,
            "company": si.company,
            "is_return": 1,
            "return_against": si.name,
            "update_stock": 0,
            "items": [
                {
                    "item_code": it.item_code,
                    "qty": -abs(it.qty),
                    "rate": it.rate,
                }
                for it in si.items
            ],
        })
        cn.flags.ignore_permissions = True
        cn.set_missing_values()
        cn.calculate_taxes_and_totals()

        # Settle immediately through the Wallet account. For a return, the
        # payment is negative (money going back to the customer's wallet).
        if settings.wallet_liability_account:
            cn.is_pos = 1
            cn.append("payments", {
                "mode_of_payment": "Wallet",
                "account": settings.wallet_liability_account,
                "amount": cn.grand_total,  # negative for a return
            })
        cn.insert()
        cn.submit()
    except Exception:
        frappe.log_error(title=f"Credit note failed for {invoice_name}",
                         message=frappe.get_traceback())