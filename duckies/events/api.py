# Copyright (c) 2026, Duckie's Sports Cafe
"""Event booking & cancellation. All money movement goes through the Sales
Invoice path (see wallet/si_hooks.py), so bookings and food orders share one
audited debit/refund mechanism."""

import frappe
from frappe import _
from frappe.utils import cint, flt, get_datetime, now_datetime

from duckies.events.tasks import get_or_create_event_item
from duckies.wallet.si_hooks import make_wallet_invoice
from duckies.wallet.api import debit, credit, get_buckets


def _lock_event(event_name: str):
    frappe.db.sql(
        "SELECT name FROM `tabCafe Event` WHERE name = %s FOR UPDATE",
        (event_name,),
    )


def book_event(customer: str, event: str, seats: int = 1):
    """Book synchronously; post accounting in the background.

    The customer's request only touches custom doctypes it is allowed to use
    (Wallet Transaction, Cafe Event, Event Booking) — it debits the wallet,
    reserves seats and creates the booking atomically. The Sales Invoice +
    Payment Entry (which read Account/GL doctypes a Website User can't access)
    are posted by a background job running as Administrator, so the customer's
    session and permissions are never involved in accounting.
    """
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

    amount = flt(ev.price) * seats

    # 1. Debit the wallet directly (bonus-first). Custom doctype only — no
    #    Account access, so no permission/session issues. Throws cleanly on
    #    insufficient balance, before any seat/booking is created.
    debit(customer, amount, "Spend", "Cafe Event", ev.name,
          remarks=_("Booking: {0} on {1}").format(ev.event_name, ev.date))

    # 2. Reserve seats + create the booking.
    ev.db_set("seats_booked", cint(ev.seats_booked) + seats,
              update_modified=False)

    booking = frappe.get_doc({
        "doctype": "Event Booking",
        "customer": customer,
        "event": ev.name,
        "seats": seats,
        "amount_paid": amount,
        "status": "Confirmed",
        "booked_on": now_datetime(),
    }).insert(ignore_permissions=True)

    # 3. Post accounting (Sales Invoice + settlement) in the background, as
    #    Administrator. Failure or unavailability of the queue never affects the
    #    confirmed booking or the already-correct wallet balance.
    _safe_enqueue(
        "duckies.events.api.post_booking_accounting",
        booking=booking.name,
    )

    return booking


@frappe.whitelist(methods=["POST"])
def staff_book_event(customer: str, event: str, seats: int = 1):
    """Staff-facing: book an event for a walk-in customer from the desk.
    Restricted to System Manager / Cafe Manager. Debits the customer's wallet
    (cash-first) exactly like the customer flow — front desk must have loaded
    the wallet first (or do an offline recharge)."""
    frappe.only_for(("System Manager", "Cafe Manager"))
    if not frappe.db.exists("Customer", customer):
        frappe.throw(_("Customer {0} not found.").format(customer))
    booking = book_event(customer, event, cint(seats))
    from duckies.wallet.api import get_buckets
    cash, bonus = get_buckets(customer)
    return {
        "booking": booking.name,
        "amount_paid": booking.amount_paid,
        "cash_balance": cash,
        "bonus_balance": bonus,
        "balance": cash + bonus,
        "message": _("Booked {0} seat(s) for {1}.").format(
            cint(seats), customer),
    }


def _safe_enqueue(method, **kwargs):
    """Enqueue a background job, but never let queue problems (no worker, no
    redis, inline-execution errors) break the customer-facing request. If the
    job can't be queued, it's logged for later reprocessing."""
    try:
        frappe.enqueue(method, queue="short", enqueue_after_commit=True,
                       **kwargs)
    except Exception:
        frappe.log_error(
            title=f"Could not enqueue {method}",
            message=frappe.get_traceback() + "\n\nkwargs: " + str(kwargs))


def post_booking_accounting(booking: str):
    """Background job: create the wallet-paid Sales Invoice for a booking and
    link it back. Runs as Administrator (jobs have no web session). Idempotent
    and non-fatal."""
    bk = frappe.get_doc("Event Booking", booking)
    if bk.sales_invoice or bk.status == "Cancelled":
        return

    ev = frappe.get_doc("Cafe Event", bk.event)
    item = ev.item or get_or_create_event_item(ev.event_name)
    try:
        si = make_wallet_invoice(
            bk.customer,
            [{"item_code": item, "qty": cint(bk.seats), "rate": flt(ev.price)}],
            remarks=_("Booking {0}: {1} on {2}").format(
                bk.name, ev.event_name, ev.date),
            skip_wallet_debit=True,  # wallet already debited synchronously
        )
        frappe.db.set_value("Event Booking", bk.name, "sales_invoice", si.name,
                            update_modified=False)
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            title=f"Booking accounting failed: {booking}",
            message=frappe.get_traceback())


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

    # 1. Refund the wallet to the original buckets (idempotent, synchronous —
    #    the customer sees their money back immediately).
    _refund_booking_to_wallet(booking)

    # 2. Release seats and close the booking.
    _lock_event(ev.name)
    ev.db_set(
        "seats_booked",
        max(0, cint(ev.seats_booked) - cint(booking.seats)),
        update_modified=False,
    )
    booking.db_set("status", "Cancelled")

    # 3. Credit Note for the books, in the background as Administrator
    #    (non-fatal; the customer-facing refund is already done).
    if booking.sales_invoice:
        _safe_enqueue(
            "duckies.events.api.post_cancellation_accounting",
            invoice=booking.sales_invoice,
        )
    return booking


def post_cancellation_accounting(invoice):
    """Background job: raise the Credit Note for a cancelled booking's invoice,
    as Administrator. Idempotent and non-fatal."""
    try:
        _make_credit_note(invoice)
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        frappe.log_error(title=f"Cancellation accounting failed: {invoice}",
                         message=frappe.get_traceback())


def _refund_booking_to_wallet(booking):
    """Post Refund credits mirroring the original Spend debits for this
    booking. Bookings debit against the Cafe Event; we mirror each bucket
    (bonus->bonus, cash->cash). Idempotent via a [refund:<booking>] tag."""
    from duckies.wallet.api import credit

    refund_tag = f"[refund:{booking.name}]"
    if frappe.db.exists("Wallet Transaction", {
        "customer": booking.customer, "direction": "Credit", "docstatus": 1,
        "transaction_type": "Refund", "remarks": ("like", f"%{refund_tag}%")}):
        return  # already refunded

    # The original spend was debited against the Cafe Event, tagged with this
    # booking's event. Match on event + amount to isolate this booking's spend.
    rows = frappe.get_all(
        "Wallet Transaction",
        filters={"customer": booking.customer, "direction": "Debit",
                 "docstatus": 1, "reference_doctype": "Cafe Event",
                 "reference_name": booking.event, "transaction_type": "Spend"},
        fields=["bucket", "amount", "creation"],
        order_by="creation desc")

    # Take the most recent spend(s) matching this booking's amount so multiple
    # bookings of the same event refund the correct one.
    target = flt(booking.amount_paid)
    per_bucket = {"Cash": 0.0, "Bonus": 0.0}
    acc = 0.0
    for r in rows:
        if acc >= target - 0.005:
            break
        per_bucket[r.bucket] = per_bucket.get(r.bucket, 0.0) + flt(r.amount)
        acc += flt(r.amount)

    # Fallback: if matching came up short, just refund amount_paid to cash.
    if acc < target - 0.005:
        per_bucket = {"Cash": target, "Bonus": 0.0}

    for bucket, bamt in per_bucket.items():
        if bamt > 0:
            credit(
                booking.customer, bamt, "Refund", bucket,
                "Event Booking", booking.name,
                remarks=_("Refund for cancelled booking {0} {1}")
                        .format(booking.name, refund_tag),
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
        from duckies.wallet.si_hooks import _elevated
        with _elevated():
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

            # Settle through the Wallet liability account so the return doesn't
            # leave a dangling outstanding. This reverses the original invoice's
            # Dr Wallet Liability into Cr — i.e. the money is accounted back into
            # "wallet liability", matching the synchronous wallet refund already
            # posted to the customer. (The return invoice does NOT re-touch the
            # wallet ledger: debit_wallet_on_submit skips is_return invoices.)
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
