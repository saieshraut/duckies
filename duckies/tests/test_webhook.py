# Copyright (c) 2026, Duckie's Sports Cafe
"""Tests for the Razorpay webhook (duckies.payments.razorpay.webhook) --
the one allow_guest=True, security-critical endpoint in the app. No real
network calls: frappe.request is stood in with a plain frappe._dict(), and
Duckies Settings' get_password is patched to a fixed test secret so the
HMAC signature check runs against a known value.
"""

import hashlib
import hmac
import json
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from duckies.payments.razorpay import webhook
from duckies.tests.test_wallet import make_test_customer

WEBHOOK_SECRET = "test-webhook-secret"


def _sign(payload: bytes) -> str:
    return hmac.new(WEBHOOK_SECRET.encode(), payload, hashlib.sha256).hexdigest()


def _event(order_id, event="payment.captured", payment_id="pay_test123"):
    return json.dumps({
        "event": event,
        "payload": {"payment": {"entity": {"order_id": order_id, "id": payment_id}}},
    }).encode()


class TestRazorpayWebhook(FrappeTestCase):
    def setUp(self):
        self.customer = make_test_customer("Webhook Test")
        self.req = frappe.get_doc({
            "doctype": "Recharge Request",
            "customer": self.customer,
            "amount": 500,
            "status": "Pending",
            "channel": "Online",
            "razorpay_order_id": f"order_{frappe.generate_hash(length=10)}",
        }).insert(ignore_permissions=True)

        original_request = getattr(frappe.local, "request", None)
        self.addCleanup(setattr, frappe.local, "request", original_request)

        settings_stub = frappe._dict({
            "get_password": lambda field, raise_exception=False: (
                WEBHOOK_SECRET if field == "razorpay_webhook_secret" else None),
        })
        patcher = patch("duckies.payments.razorpay._settings",
                        return_value=settings_stub)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _request(self, payload: bytes, signature: str):
        frappe.local.request = frappe._dict(
            data=payload, headers={"X-Razorpay-Signature": signature})

    def test_bad_signature_is_rejected_and_wallet_untouched(self):
        payload = _event(self.req.razorpay_order_id)
        self._request(payload, "not-the-real-signature")
        with self.assertRaises(frappe.PermissionError):
            webhook()
        self.req.reload()
        self.assertEqual(self.req.status, "Pending")

    def test_valid_signature_settles_the_recharge(self):
        payload = _event(self.req.razorpay_order_id)
        self._request(payload, _sign(payload))
        result = webhook()
        self.assertEqual(result, "ok")
        self.req.reload()
        self.assertEqual(self.req.status, "Paid")
        self.assertEqual(self.req.razorpay_payment_id, "pay_test123")

    def test_unknown_order_id_is_ignored_not_fatal(self):
        payload = _event("order_does_not_exist")
        self._request(payload, _sign(payload))
        self.assertEqual(webhook(), "unknown-order")

    def test_webhook_retry_is_idempotent(self):
        payload = _event(self.req.razorpay_order_id)
        self._request(payload, _sign(payload))
        webhook()
        webhook()  # Razorpay retries the same event on a delayed 200
        self.req.reload()
        self.assertEqual(self.req.status, "Paid")

    def test_payment_failed_marks_pending_request_failed(self):
        payload = _event(self.req.razorpay_order_id, event="payment.failed")
        self._request(payload, _sign(payload))
        webhook()
        self.req.reload()
        self.assertEqual(self.req.status, "Failed")

    def test_missing_secret_configured_is_rejected(self):
        payload = _event(self.req.razorpay_order_id)
        self._request(payload, _sign(payload))
        with patch("duckies.payments.razorpay._settings",
                   return_value=frappe._dict({
                       "get_password": lambda field, raise_exception=False: None,
                   })):
            with self.assertRaises(frappe.PermissionError):
                webhook()
