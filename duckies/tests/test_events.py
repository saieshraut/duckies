# Copyright (c) 2026, Duckie's Sports Cafe
"""Tests for event booking & cancellation (duckies.events.api).

Stays clear of Company/Account setup: book_event's accounting (Sales Invoice
+ Payment Entry) is posted by a background job enqueued with
enqueue_after_commit=True (see events/api.py), which never actually fires
inside a test's rolled-back transaction — so these tests exercise the
synchronous wallet-debit + seat-reservation + refund logic in isolation,
on any site the app is installed on.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, getdate, now_datetime

from duckies.events.api import book_event, cancel_booking
from duckies.tests.test_wallet import make_test_customer
from duckies.wallet.api import credit, get_buckets


def make_test_event(price=300, capacity=2, hours_from_now=48, **kwargs):
    """A Cafe Event ``hours_from_now`` in the future, so cancellation-cutoff
    checks are deterministic regardless of wall-clock time or Duckies
    Settings' global default cutoff."""
    space = frappe.get_all("Cafe Space", limit=1, pluck="name")
    if not space:
        frappe.throw("No Cafe Space found — run after_install first.")
    dt = add_to_date(now_datetime(), hours=hours_from_now)
    fields = {
        "doctype": "Cafe Event",
        "event_name": f"Test Event {frappe.generate_hash(length=6)}",
        "space": space[0],
        "date": getdate(dt),
        "start_time": dt.strftime("%H:%M:%S"),
        "price": price,
        "capacity": capacity,
        "status": "Upcoming",
        "is_cancellable": 1,
        "cancellation_cutoff_hours": 1,
        "refund_type": "Percentage",
        "refund_percentage": 100,
    }
    fields.update(kwargs)
    return frappe.get_doc(fields).insert(ignore_permissions=True)


class TestBookEvent(FrappeTestCase):
    def setUp(self):
        self.customer = make_test_customer("Booking Test")
        self.event = make_test_event(price=300, capacity=2)

    def test_book_event_debits_wallet_and_reserves_seats(self):
        credit(self.customer, 1000, "Recharge", "Cash")
        booking = book_event(self.customer, self.event.name, 2)

        self.assertEqual(booking.amount_paid, 600)
        cash, bonus = get_buckets(self.customer)
        self.assertEqual(cash, 400)

        self.event.reload()
        self.assertEqual(self.event.seats_booked, 2)

    def test_book_event_fails_on_insufficient_balance(self):
        credit(self.customer, 100, "Recharge", "Cash")
        with self.assertRaises(frappe.ValidationError):
            book_event(self.customer, self.event.name, 1)

        self.event.reload()
        self.assertEqual(self.event.seats_booked, 0)

    def test_book_event_fails_when_not_enough_seats_left(self):
        credit(self.customer, 10000, "Recharge", "Cash")
        book_event(self.customer, self.event.name, 2)  # fills capacity (2)

        other = make_test_customer("Booking Test Overflow")
        credit(other, 10000, "Recharge", "Cash")
        with self.assertRaises(frappe.ValidationError):
            book_event(other, self.event.name, 1)


class TestCancelBooking(FrappeTestCase):
    def setUp(self):
        self.customer = make_test_customer("Cancel Test")
        self.event = make_test_event(price=300, capacity=5)
        credit(self.customer, 1000, "Recharge", "Cash")
        self.booking = book_event(self.customer, self.event.name, 2)

    def test_cancel_refunds_wallet_and_releases_seats(self):
        cancelled = cancel_booking(self.customer, self.booking.name)
        self.assertEqual(cancelled.refund_amount, 600)

        cash, bonus = get_buckets(self.customer)
        self.assertEqual(cash, 1000)  # fully refunded (100% policy)

        self.event.reload()
        self.assertEqual(self.event.seats_booked, 0)

        self.booking.reload()
        self.assertEqual(self.booking.status, "Cancelled")

    def test_cancel_rejects_someone_elses_booking(self):
        other = make_test_customer("Cancel Test Other")
        with self.assertRaises(frappe.PermissionError):
            cancel_booking(other, self.booking.name)

    def test_cancel_twice_raises(self):
        cancel_booking(self.customer, self.booking.name)
        with self.assertRaises(frappe.ValidationError):
            cancel_booking(self.customer, self.booking.name)

    def test_partial_refund_policy_refunds_only_the_policy_amount(self):
        event = make_test_event(price=200, capacity=5, refund_percentage=50)
        booking = book_event(self.customer, event.name, 1)
        cash_before, _ = get_buckets(self.customer)

        cancelled = cancel_booking(self.customer, booking.name)
        self.assertEqual(cancelled.refund_amount, 100)  # 50% of 200

        cash_after, _ = get_buckets(self.customer)
        self.assertEqual(cash_after, cash_before + 100)

    def test_cancel_blocked_after_cutoff(self):
        # Starts in 1 hour, but cancellations close 2 hours before start —
        # already past the cutoff.
        event = make_test_event(price=200, capacity=5, hours_from_now=1,
                                cancellation_cutoff_hours=2)
        booking = book_event(self.customer, event.name, 1)
        with self.assertRaises(frappe.ValidationError):
            cancel_booking(self.customer, booking.name)

    def test_cancel_blocked_when_not_cancellable(self):
        event = make_test_event(price=200, capacity=5, is_cancellable=0)
        booking = book_event(self.customer, event.name, 1)
        with self.assertRaises(frappe.ValidationError):
            cancel_booking(self.customer, booking.name)
