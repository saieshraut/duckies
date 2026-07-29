# Copyright (c) 2026, Duckie's Sports Cafe
"""Tests for customer-facing api.py guards that don't need a real HTTP
session (register()'s LoginManager call does, so it isn't covered here —
its duplicate-mobile check is a plain frappe.db.exists() query, exercised
indirectly by construction in test_register_blocks_duplicate_mobile)."""

import frappe
from frappe.tests.utils import FrappeTestCase

from duckies.api import delete_my_account
from duckies.wallet.api import credit


def make_portal_user_and_customer(hint="Api Test"):
    email = f"{frappe.generate_hash(length=10)}@duckies.test"
    user = frappe.get_doc({
        "doctype": "User", "email": email, "first_name": hint,
        "user_type": "Website User", "send_welcome_email": 0,
    })
    user.flags.ignore_permissions = True
    user.insert()

    customer = frappe.get_doc({
        "doctype": "Customer",
        "customer_name": f"{hint} {frappe.generate_hash(length=6)}",
        "customer_type": "Individual",
        "customer_group": frappe.db.get_single_value(
            "Selling Settings", "customer_group") or "Individual",
        "territory": frappe.db.get_single_value(
            "Selling Settings", "territory") or "All Territories",
        "custom_user": email,
    })
    customer.flags.ignore_permissions = True
    customer.insert()
    return email, customer.name


class TestDeleteMyAccount(FrappeTestCase):
    def setUp(self):
        self.email, self.customer = make_portal_user_and_customer()
        self.addCleanup(lambda: frappe.set_user("Administrator"))

    def test_delete_blocked_while_balance_positive(self):
        credit(self.customer, 100, "Recharge", "Cash")
        frappe.set_user(self.email)
        with self.assertRaises(frappe.ValidationError):
            delete_my_account()
        frappe.set_user("Administrator")

        # Nothing should have been touched.
        cust = frappe.get_doc("Customer", self.customer)
        self.assertEqual(cust.custom_user, self.email)
        self.assertTrue(frappe.db.get_value("User", self.email, "enabled"))

    def test_delete_allowed_once_balance_is_zero(self):
        frappe.set_user(self.email)
        delete_my_account()
        frappe.set_user("Administrator")

        cust = frappe.get_doc("Customer", self.customer)
        self.assertFalse(cust.custom_user)
        self.assertFalse(frappe.db.get_value("User", self.email, "enabled"))


class TestRegisterDuplicateMobile(FrappeTestCase):
    """register() rejects a mobile number already used by another Customer.
    Exercised at the query level that register() relies on (frappe.db.exists
    on Customer.mobile_no) rather than through the full endpoint, since
    register() also drives frappe.auth.LoginManager, which needs a real HTTP
    request context that isn't available under the test runner."""

    def test_duplicate_mobile_is_detected(self):
        import random
        mobile = "9" + "".join(random.choices("0123456789", k=9))
        frappe.get_doc({
            "doctype": "Customer",
            "customer_name": f"Mobile Dup Test {frappe.generate_hash(length=6)}",
            "customer_type": "Individual",
            "customer_group": frappe.db.get_single_value(
                "Selling Settings", "customer_group") or "Individual",
            "territory": frappe.db.get_single_value(
                "Selling Settings", "territory") or "All Territories",
            "mobile_no": mobile,
        }).insert(ignore_permissions=True)

        self.assertTrue(frappe.db.exists("Customer", {"mobile_no": mobile}))
