# Copyright (c) 2026, Duckie's Sports Cafe
"""Shared cancellation-policy rules for Cafe Event / Event Template.

Both doctypes carry the same policy fields (is_cancellable,
cancellation_cutoff_hours, refund_type, refund_percentage,
refund_flat_amount) so admins can set a policy on a template and still
override it on an individual occurrence. This module centralises the
validation and refund math so events/api.py and both doctype controllers
agree on what a "policy-bearing" doc looks like.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt


def validate_cancellation_policy(doc):
    if doc.get("cancellation_cutoff_hours") and cint(doc.cancellation_cutoff_hours) < 0:
        frappe.throw(_("Cancellation Cutoff Hours cannot be negative."))

    if doc.get("refund_type") == "Flat":
        if flt(doc.get("refund_flat_amount")) < 0:
            frappe.throw(_("Refund Flat Amount cannot be negative."))
    else:
        pct = flt(doc.get("refund_percentage"))
        if pct < 0 or pct > 100:
            frappe.throw(_("Refund Percentage must be between 0 and 100."))


def get_cutoff_hours(doc) -> int:
    """Event/template override wins; otherwise fall back to the global
    default in Duckies Settings."""
    if doc.get("cancellation_cutoff_hours"):
        return cint(doc.cancellation_cutoff_hours)
    return cint(frappe.get_cached_doc("Duckies Settings").cancellation_cutoff_hours)


def compute_refund_amount(doc, amount_paid, seats=1) -> float:
    """Refund owed to the customer for cancelling a booking of `doc` (a Cafe
    Event), given what they actually paid. Always clamped to [0, amount_paid]
    so a misconfigured policy can never refund more than was collected."""
    amount_paid = flt(amount_paid)
    if doc.get("refund_type") == "Flat":
        refund = flt(doc.get("refund_flat_amount")) * cint(seats)
    else:
        pct = doc.get("refund_percentage")
        pct = 100.0 if pct in (None, "") else flt(pct)
        refund = amount_paid * pct / 100.0
    return max(0.0, min(refund, amount_paid))
