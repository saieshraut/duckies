# Copyright (c) 2026, Duckie's Sports Cafe
"""Tests for wallet expiry, reminder catch-up tracking & breakage
(duckies.wallet.expiry).

_wallets_with_balance() sweeps every Customer with a positive balance, so
tests that call the scheduler entry points patch it to return only the
customer under test -- otherwise any other wallet balance already on this
site (leftover smoke-test data, real usage) would get swept up too, and
send_expiry_reminders would try to actually email it.

expiry_date_for() is also patched to a fixed days-from-today value in the
sweep tests, so the threshold/catch-up logic is verified precisely without
depending on calendar arithmetic (add_months day-of-month edge cases) or
today's actual date.

expire_lapsed_wallets() calls frappe.db.commit() internally (it's a
scheduler job) -- that would break FrappeTestCase's rollback-based isolation
and leave permanent rows in the site, so its test patches frappe.db.commit
to a no-op for the duration of the call.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate, now_datetime, today

from duckies.tests.test_wallet import make_test_customer
from duckies.wallet.api import credit, get_buckets
from duckies.wallet.expiry import (
    _parse_sent_reminders,
    _save_sent_reminders,
    expire_lapsed_wallets,
    send_expiry_reminders,
)

ROW_FIELDS = ["name", "customer_name", "email_id", "custom_wallet_cash",
              "custom_wallet_bonus", "custom_wallet_balance",
              "custom_wallet_last_activity", "custom_wallet_reminders_sent"]


def _row_for(customer):
    return frappe.db.get_value("Customer", customer, ROW_FIELDS, as_dict=True)


class TestReminderThresholdTracking(FrappeTestCase):
    """Pure bookkeeping: which day-thresholds have already been notified for
    the wallet's CURRENT expiry cycle."""

    def test_empty_when_nothing_sent_yet(self):
        self.assertEqual(_parse_sent_reminders(None, "2026-08-01"), set())
        self.assertEqual(_parse_sent_reminders("", "2026-08-01"), set())

    def test_parses_thresholds_for_the_matching_cycle(self):
        self.assertEqual(_parse_sent_reminders("2026-08-01|30,7", "2026-08-01"),
                         {30, 7})

    def test_stale_cycle_is_discarded(self):
        # The wallet's expiry date moved on (a recharge/spend reset the
        # clock) since the last reminder -- that's a new cycle, so nothing
        # already sent for the OLD cycle carries over.
        self.assertEqual(_parse_sent_reminders("2026-08-01|30,7", "2026-09-15"),
                         set())

    def test_save_and_parse_round_trip(self):
        customer = make_test_customer("Reminder Tracking Test")
        _save_sent_reminders(customer, "2026-08-01", {30, 7})
        raw = frappe.db.get_value("Customer", customer,
                                  "custom_wallet_reminders_sent")
        self.assertEqual(_parse_sent_reminders(raw, "2026-08-01"), {30, 7})


class TestSendExpiryReminders(FrappeTestCase):
    def setUp(self):
        self.customer = make_test_customer("Expiry Reminder Test")
        credit(self.customer, 500, "Recharge", "Cash")
        # credit() already stamped last_activity, but pin it explicitly so
        # the test doesn't depend on when credit() happened to run.
        frappe.db.set_value("Customer", self.customer,
                            "custom_wallet_last_activity", now_datetime(),
                            update_modified=False)

    def _sweep(self, days_left):
        row = _row_for(self.customer)
        target_exp = add_days(getdate(today()), days_left)
        with patch("duckies.wallet.expiry._wallets_with_balance",
                  return_value=[row]), \
             patch("duckies.wallet.expiry.expiry_date_for",
                  return_value=target_exp):
            send_expiry_reminders()

    def _tracking(self):
        return frappe.db.get_value("Customer", self.customer,
                                   "custom_wallet_reminders_sent")

    def test_reminder_sent_when_within_threshold(self):
        self._sweep(days_left=25)  # inside the default "30,7" schedule
        raw = self._tracking()
        self.assertIsNotNone(raw)
        self.assertIn("30", raw.split("|", 1)[1].split(","))

    def test_reminder_not_sent_when_nowhere_near_expiry(self):
        self._sweep(days_left=60)
        self.assertFalse(self._tracking())

    def test_same_threshold_is_never_resent_twice_in_one_cycle(self):
        self._sweep(days_left=25)
        first = self._tracking()
        self._sweep(days_left=25)  # nothing changed; still 25 days out
        self.assertEqual(first, self._tracking())

    def test_catch_up_after_missed_run_marks_all_moot_thresholds_sent(self):
        # Scheduler missed the 30-day mark entirely; by the time it next
        # runs only 5 days are left. One reminder fires (the most urgent),
        # but BOTH thresholds must be recorded as sent so neither fires
        # again for this cycle.
        self._sweep(days_left=5)
        raw = self._tracking()
        self.assertIsNotNone(raw)
        cycle_key, days_csv = raw.split("|", 1)
        self.assertEqual({int(d) for d in days_csv.split(",")}, {30, 7})

    def test_already_lapsed_wallet_gets_no_reminder(self):
        # Negative days-left means it's already expired -- that's
        # expire_lapsed_wallets' job, not a reminder.
        self._sweep(days_left=-1)
        self.assertFalse(self._tracking())


class TestExpireLapsedWallets(FrappeTestCase):
    def setUp(self):
        self.customer = make_test_customer("Expiry Lapse Test")
        credit(self.customer, 800, "Recharge", "Cash")
        credit(self.customer, 200, "Bonus", "Bonus")

    def _run(self, days_left):
        row = _row_for(self.customer)
        target_exp = add_days(getdate(today()), days_left)
        # expire_lapsed_wallets() ends with frappe.db.commit() -- swallow it
        # so FrappeTestCase can still roll this test back.
        with patch("duckies.wallet.expiry._wallets_with_balance",
                  return_value=[row]), \
             patch("duckies.wallet.expiry.expiry_date_for",
                  return_value=target_exp), \
             patch("frappe.db.commit"):
            expire_lapsed_wallets()

    def test_lapsed_wallet_is_debited_to_zero(self):
        self._run(days_left=-1)  # expiry date was yesterday
        cash, bonus = get_buckets(self.customer)
        self.assertEqual(cash, 0)
        self.assertEqual(bonus, 0)

    def test_not_yet_lapsed_wallet_is_untouched(self):
        self._run(days_left=10)  # still valid
        cash, bonus = get_buckets(self.customer)
        self.assertEqual(cash, 800)
        self.assertEqual(bonus, 200)
