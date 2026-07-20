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
    """Full refund if cancelled before the cutoff (Duckies Settings)."""
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

    # Cancelling the invoice triggers the wallet Refund credit via hook —
    # one refund path for everything.
    if booking.sales_invoice:
        si = frappe.get_doc("Sales Invoice", booking.sales_invoice)
        if si.docstatus == 1:
            si.flags.ignore_permissions = True
            si.cancel()

    _lock_event(ev.name)
    ev.db_set(
        "seats_booked",
        max(0, cint(ev.seats_booked) - cint(booking.seats)),
        update_modified=False,
    )
    booking.db_set("status", "Cancelled")
    return booking
