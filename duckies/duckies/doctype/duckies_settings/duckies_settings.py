# Copyright (c) 2026, Duckie's Sports Cafe

import frappe
from frappe import _
from frappe.model.document import Document

# Transactional doctypes wiped by reset_transactional_data(), plus the
# cached/denormalized fields elsewhere that must be zeroed alongside them so
# wallet balances and event seat counts don't go stale.
RESET_DOCTYPES = (
    "Wallet Transaction",
    "Wallet Refund Request",
    "Recharge Request",
    "Event Booking",
)


class DuckiesSettings(Document):
    pass


@frappe.whitelist()
def reset_transactional_data():
    """Wipe all wallet/booking transactional data. System Manager only.

    Also resets the cached Customer wallet balances and Cafe Event
    seats_booked counters, since both are denormalized from the records
    being deleted here and would otherwise go stale.
    """
    frappe.only_for("System Manager")

    for doctype in RESET_DOCTYPES:
        frappe.db.delete(doctype)

    frappe.db.sql("""
        UPDATE `tabCustomer`
        SET custom_wallet_cash = 0,
            custom_wallet_bonus = 0,
            custom_wallet_balance = 0,
            custom_wallet_last_activity = NULL
    """)
    frappe.db.sql("UPDATE `tabCafe Event` SET seats_booked = 0")

    frappe.db.commit()
    frappe.clear_cache()

    return _("All wallet transactions, refund requests, recharge requests "
              "and event bookings have been deleted, and wallet balances / "
              "event seat counts reset.")
