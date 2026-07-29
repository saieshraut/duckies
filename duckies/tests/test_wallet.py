# Copyright (c) 2026, Duckie's Sports Cafe
"""Tests for the core wallet ledger (duckies.wallet.api).

Deliberately stays clear of Company/Account setup: credit()/debit() and
forfeit_bonus() only touch the Customer's wallet custom fields + the Wallet
Transaction ledger, and the accounting postings they trigger
(post_recharge_accounting, etc.) are non-fatal by design when Duckies
Settings has no accounts configured — so these tests exercise the wallet
math in isolation, on any site the app is installed on.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from duckies.wallet.api import (
    credit,
    debit,
    forfeit_bonus,
    get_applicable_bonus,
    get_buckets,
)


def make_test_customer(name_hint="Wallet Test") -> str:
    customer = frappe.get_doc({
        "doctype": "Customer",
        "customer_name": f"{name_hint} {frappe.generate_hash(length=8)}",
        "customer_type": "Individual",
        "customer_group": frappe.db.get_single_value(
            "Selling Settings", "customer_group") or "Individual",
        "territory": frappe.db.get_single_value(
            "Selling Settings", "territory") or "All Territories",
    }).insert(ignore_permissions=True)
    return customer.name


class TestWalletLedger(FrappeTestCase):
    def setUp(self):
        self.customer = make_test_customer()

    def test_credit_adds_to_the_right_bucket(self):
        credit(self.customer, 1000, "Recharge", "Cash")
        credit(self.customer, 250, "Bonus", "Bonus")
        cash, bonus = get_buckets(self.customer)
        self.assertEqual(cash, 1000)
        self.assertEqual(bonus, 250)

    def test_debit_defaults_to_cash_first_then_bonus(self):
        credit(self.customer, 100, "Recharge", "Cash")
        credit(self.customer, 100, "Bonus", "Bonus")

        # Spend 150: should drain Cash (100) then take 50 from Bonus.
        debit(self.customer, 150, "Spend")
        cash, bonus = get_buckets(self.customer)
        self.assertEqual(cash, 0)
        self.assertEqual(bonus, 50)

    def test_debit_with_explicit_bucket_never_touches_the_other(self):
        credit(self.customer, 500, "Recharge", "Cash")
        credit(self.customer, 500, "Bonus", "Bonus")

        debit(self.customer, 200, "Adjustment", bucket="Bonus")
        cash, bonus = get_buckets(self.customer)
        self.assertEqual(cash, 500)  # untouched
        self.assertEqual(bonus, 300)

    def test_debit_with_explicit_bucket_fails_even_if_other_bucket_covers_it(self):
        credit(self.customer, 1000, "Recharge", "Cash")
        # No bonus at all — a Bonus-only debit must fail even though Cash
        # could easily cover it, because bucket= means "only this bucket".
        with self.assertRaises(frappe.ValidationError):
            debit(self.customer, 50, "Adjustment", bucket="Bonus")
        cash, bonus = get_buckets(self.customer)
        self.assertEqual(cash, 1000)
        self.assertEqual(bonus, 0)

    def test_debit_insufficient_balance_throws_and_changes_nothing(self):
        credit(self.customer, 100, "Recharge", "Cash")
        with self.assertRaises(frappe.ValidationError):
            debit(self.customer, 101, "Spend")
        cash, bonus = get_buckets(self.customer)
        self.assertEqual(cash, 100)
        self.assertEqual(bonus, 0)

    def test_forfeit_bonus_zeroes_bonus_only(self):
        credit(self.customer, 1000, "Recharge", "Cash")
        credit(self.customer, 300, "Bonus", "Bonus")

        txn = forfeit_bonus(self.customer, remarks="test forfeiture")
        self.assertIsNotNone(txn)
        self.assertEqual(txn.transaction_type, "Forfeiture")
        self.assertEqual(txn.amount, 300)

        cash, bonus = get_buckets(self.customer)
        self.assertEqual(cash, 1000)  # untouched
        self.assertEqual(bonus, 0)

    def test_forfeit_bonus_is_a_noop_when_bonus_already_zero(self):
        credit(self.customer, 1000, "Recharge", "Cash")
        self.assertIsNone(forfeit_bonus(self.customer))
        cash, bonus = get_buckets(self.customer)
        self.assertEqual(cash, 1000)
        self.assertEqual(bonus, 0)


class TestApplicableBonusDeterminism(FrappeTestCase):
    def setUp(self):
        self.offers = []

    def tearDown(self):
        for name in self.offers:
            frappe.delete_doc("Recharge Offer", name, force=True,
                              ignore_permissions=True)

    def _make_offer(self, offer_name, min_amount, bonus_amount):
        doc = frappe.get_doc({
            "doctype": "Recharge Offer",
            "offer_name": offer_name,
            "min_recharge_amount": min_amount,
            "bonus_type": "Fixed Amount",
            "bonus_amount": bonus_amount,
            "is_active": 1,
        }).insert(ignore_permissions=True)
        self.offers.append(doc.name)
        return doc.name

    def test_tie_between_equal_offers_is_deterministic(self):
        # Two active offers, same qualifying bonus at this amount — repeated
        # calls must resolve to the same offer every time (no dependency on
        # unspecified DB row order).
        self._make_offer("ZZZ Tie Offer", 1000, 500)
        self._make_offer("AAA Tie Offer", 1000, 500)

        results = {get_applicable_bonus(2000) for _ in range(5)}
        self.assertEqual(len(results), 1, "get_applicable_bonus must be deterministic")
        bonus, offer = next(iter(results))
        self.assertEqual(bonus, 500)
        self.assertEqual(offer, "AAA Tie Offer")  # order_by="name asc"
