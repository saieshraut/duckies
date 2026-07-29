# Copyright (c) 2026, Duckie's Sports Cafe
"""Regression test for the critical bonus-forfeiture bug: a customer must
never be able to recharge, collect a bonus, refund the cash straight back
out, and keep the bonus as free spendable credit.

Exercises duckies.payments.razorpay.process_refund directly (rather than
apply_recharge -> real Razorpay call) so it runs without network access:
the Razorpay reversal branch only fires when the Wallet Refund Request has
`refund_to == "Original Payment Source"` AND an `original_recharge` link, so
leaving `original_recharge` unset exercises the full wallet-side flow
(the part this bug lives in) without touching Razorpay.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from duckies.payments.razorpay import process_refund
from duckies.tests.test_wallet import make_test_customer
from duckies.wallet.api import apply_recharge, get_buckets


class TestRefundForfeitsBonus(FrappeTestCase):
    def setUp(self):
        self.customer = make_test_customer("Refund Exploit Test")

    def _request_refund(self, amount, refund_to="Bank Transfer"):
        req = frappe.get_doc({
            "doctype": "Wallet Refund Request",
            "customer": self.customer,
            "amount": amount,
            "reason": "test",
            "status": "Requested",
            "refund_to": refund_to,  # avoid the Razorpay branch in tests
        })
        req.flags.ignore_permissions = True
        req.insert()
        req.submit()  # "submit" == staff approval
        return req.name

    def test_full_cash_refund_forfeits_remaining_bonus(self):
        # Recharge 2000 cash + 500 bonus (mirrors the "load 2000 get 500"
        # offer from the README's own testing checklist).
        cash_txn, bonus_txn, bonus, _je = apply_recharge(
            self.customer, 2000, remarks="test recharge", offer="none")
        # Apply the bonus directly so this test doesn't depend on a
        # Recharge Offer record existing on the site.
        from duckies.wallet.api import credit
        credit(self.customer, 500, "Bonus", "Bonus", remarks="test bonus")

        cash, bonus = get_buckets(self.customer)
        self.assertEqual(cash, 2000)
        self.assertEqual(bonus, 500)

        # Customer asks for, and staff processes, a FULL cash refund.
        refund_name = self._request_refund(2000)
        result = process_refund(refund_name)

        cash, bonus = get_buckets(self.customer)
        self.assertEqual(cash, 0, "cash should be fully refunded")
        self.assertEqual(
            bonus, 0,
            "BONUS MUST BE FORFEITED on a cash-out refund — a customer must "
            "never get their real money back AND keep live promotional "
            "credit funded by the same recharge.")

        req = frappe.get_doc("Wallet Refund Request", refund_name)
        self.assertEqual(req.bonus_forfeited, 500)
        self.assertTrue(req.bonus_forfeited_transaction)
        forfeiture = frappe.get_doc("Wallet Transaction",
                                    req.bonus_forfeited_transaction)
        self.assertEqual(forfeiture.transaction_type, "Forfeiture")
        self.assertEqual(forfeiture.direction, "Debit")
        self.assertEqual(forfeiture.bucket, "Bonus")
        self.assertEqual(forfeiture.amount, 500)

    def test_refund_with_no_bonus_is_unaffected(self):
        apply_recharge(self.customer, 1000, remarks="test recharge",
                       offer="none")
        refund_name = self._request_refund(400)
        process_refund(refund_name)

        cash, bonus = get_buckets(self.customer)
        self.assertEqual(cash, 600)
        self.assertEqual(bonus, 0)
        req = frappe.get_doc("Wallet Refund Request", refund_name)
        self.assertFalse(req.bonus_forfeited)
        self.assertFalse(req.bonus_forfeited_transaction)

    def test_refund_cannot_exceed_cash_balance(self):
        apply_recharge(self.customer, 500, remarks="test recharge",
                       offer="none")
        from duckies.wallet.api import credit
        credit(self.customer, 1000, "Bonus", "Bonus", remarks="test bonus")

        # Even though cash+bonus = 1500, a refund request for more than the
        # 500 cash balance must be rejected outright — the doc-level
        # validate() check in WalletRefundRequest enforces this on insert.
        with self.assertRaises(frappe.ValidationError):
            self._request_refund(600)

    def test_process_refund_is_idempotent_on_retry(self):
        apply_recharge(self.customer, 1000, remarks="test recharge",
                       offer="none")
        from duckies.wallet.api import credit
        credit(self.customer, 200, "Bonus", "Bonus", remarks="test bonus")

        refund_name = self._request_refund(1000)
        process_refund(refund_name)
        cash, bonus = get_buckets(self.customer)
        self.assertEqual(cash, 0)
        self.assertEqual(bonus, 0)

        # Calling again (e.g. a retried request) must not double-refund or
        # re-forfeit anything that's already gone.
        result = process_refund(refund_name)
        self.assertEqual(result["message"], "Already processed.")
        cash, bonus = get_buckets(self.customer)
        self.assertEqual(cash, 0)
        self.assertEqual(bonus, 0)
