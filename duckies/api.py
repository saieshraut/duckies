# Copyright (c) 2026, Duckie's Sports Cafe
"""Customer-facing API for the web app.

Portal users get NO direct DocType permissions — they interact only through
these endpoints, and the Customer is always resolved server-side from the
session. That way nobody can hit the generic REST API and edit their own
wallet balance.

All endpoints: POST /api/method/duckies.api.<function>
(GET also works for the read-only ones.)
"""

import json

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, today, validate_email_address

from duckies.wallet.api import get_balance, get_customer_for_user


# --------------------------------------------------------------------------
# Auth
# --------------------------------------------------------------------------

@frappe.whitelist(allow_guest=True, methods=["POST"])
def register(full_name: str, email: str, mobile: str, password: str):
    """Create a Website User + linked Customer, then log them in."""
    email = (email or "").strip().lower()
    validate_email_address(email, throw=True)
    if not (full_name or "").strip():
        frappe.throw(_("Please tell us your name."))
    if len(password or "") < 8:
        frappe.throw(_("Password must be at least 8 characters."))
    if frappe.db.exists("User", email):
        frappe.throw(_("An account with this email already exists. Please log in."))

    first, _sep, last = full_name.strip().partition(" ")
    user = frappe.get_doc({
        "doctype": "User",
        "email": email,
        "first_name": first,
        "last_name": last,
        "mobile_no": mobile,
        "user_type": "Website User",
        "send_welcome_email": 0,
    })
    user.flags.ignore_permissions = True
    user.insert()
    user.new_password = password
    user.save(ignore_permissions=True)

    customer = frappe.get_doc({
        "doctype": "Customer",
        "customer_name": full_name.strip(),
        "customer_type": "Individual",
        "customer_group": frappe.db.get_single_value(
            "Selling Settings", "customer_group") or "Individual",
        "territory": frappe.db.get_single_value(
            "Selling Settings", "territory") or "All Territories",
        "mobile_no": mobile,
        "email_id": email,
        "custom_user": email,
    })
    customer.flags.ignore_permissions = True
    customer.insert()

    # Log the new customer straight in
    from frappe.auth import LoginManager
    lm = LoginManager()
    lm.authenticate(user=email, pwd=password)
    lm.post_login()

    return {"message": _("Welcome to Duckie's!"), "customer": customer.name}
    # Login: use Frappe's built-in POST /api/method/login (usr, pwd)
    # Logout: POST /api/method/logout


@frappe.whitelist()
def get_profile():
    customer = get_customer_for_user()
    c = frappe.db.get_value(
        "Customer", customer,
        ["name", "customer_name", "mobile_no", "email_id",
         "custom_wallet_balance"],
        as_dict=True,
    )
    return {
        "customer": c.name,
        "name": c.customer_name,
        "mobile": c.mobile_no,
        "email": c.email_id,
        "wallet_balance": flt(c.custom_wallet_balance),
    }


# --------------------------------------------------------------------------
# Wallet
# --------------------------------------------------------------------------

@frappe.whitelist()
def balance():
    return {"balance": get_balance(get_customer_for_user())}


@frappe.whitelist()
def transactions(limit: int = 20, start: int = 0):
    customer = get_customer_for_user()
    rows = frappe.get_all(
        "Wallet Transaction",
        filters={"customer": customer, "docstatus": 1},
        fields=["name", "posting_datetime", "transaction_type", "direction",
                "amount", "balance_after", "remarks"],
        order_by="posting_datetime desc, creation desc",
        limit_start=cint(start), limit_page_length=min(cint(limit) or 20, 100),
    )
    return {"balance": get_balance(customer), "transactions": rows}


@frappe.whitelist()
def active_offers():
    rows = frappe.get_all(
        "Recharge Offer",
        filters={"is_active": 1},
        fields=["offer_name", "min_recharge_amount", "bonus_type",
                "bonus_amount", "bonus_percent", "valid_from", "valid_to"],
        order_by="min_recharge_amount asc",
    )
    t = today()
    return [r for r in rows
            if (not r.valid_from or str(r.valid_from) <= t)
            and (not r.valid_to or str(r.valid_to) >= t)]


# --------------------------------------------------------------------------
# Spaces & events
# --------------------------------------------------------------------------

@frappe.whitelist(allow_guest=True)
def spaces():
    return frappe.get_all(
        "Cafe Space", filters={"is_active": 1},
        fields=["name", "space_name", "tagline", "description", "capacity",
                "image", "is_bookable"],
        order_by="creation asc",
    )


@frappe.whitelist(allow_guest=True)
def events(space: str | None = None, from_date: str | None = None,
           to_date: str | None = None, limit: int = 50):
    filters = {
        "status": "Upcoming",
        "date": (">=", getdate(from_date) if from_date else getdate(today())),
    }
    if space:
        filters["space"] = space
    if to_date:
        filters["date"] = ("between", [filters["date"][1], getdate(to_date)])

    rows = frappe.get_all(
        "Cafe Event", filters=filters,
        fields=["name", "event_name", "space", "date", "start_time",
                "end_time", "price", "capacity", "seats_booked", "image",
                "description"],
        order_by="date asc, start_time asc",
        limit_page_length=min(cint(limit) or 50, 200),
    )
    for r in rows:
        r["seats_left"] = max(0, cint(r.capacity) - cint(r.seats_booked))
    return rows


@frappe.whitelist(methods=["POST"])
def book_event(event: str, seats: int = 1):
    from duckies.events.api import book_event as _book
    customer = get_customer_for_user()
    booking = _book(customer, event, cint(seats))
    return {
        "booking": booking.name,
        "amount_paid": booking.amount_paid,
        "balance": get_balance(customer),
        "message": _("Booking confirmed! See you at Duckie's."),
    }


@frappe.whitelist(methods=["POST"])
def cancel_booking(booking: str):
    from duckies.events.api import cancel_booking as _cancel
    customer = get_customer_for_user()
    _cancel(customer, booking)
    return {"balance": get_balance(customer),
            "message": _("Booking cancelled and wallet refunded.")}


@frappe.whitelist()
def my_bookings(limit: int = 20, start: int = 0):
    customer = get_customer_for_user()
    rows = frappe.get_all(
        "Event Booking", filters={"customer": customer},
        fields=["name", "event", "seats", "amount_paid", "status", "booked_on"],
        order_by="booked_on desc",
        limit_start=cint(start), limit_page_length=min(cint(limit) or 20, 100),
    )
    for r in rows:
        ev = frappe.db.get_value(
            "Cafe Event", r.event,
            ["event_name", "space", "date", "start_time"], as_dict=True)
        r.update(ev or {})
    return rows


# --------------------------------------------------------------------------
# Menu & food orders
# --------------------------------------------------------------------------

@frappe.whitelist(allow_guest=True)
def menu():
    root = (frappe.get_cached_doc("Duckies Settings").menu_root_item_group
            or "All Item Groups")
    groups = [root] + frappe.get_all(
        "Item Group", filters={"parent_item_group": root}, pluck="name")
    # include one more level (e.g. Kitchen & Bar → Cocktails → Signature)
    for g in list(groups):
        groups += frappe.get_all(
            "Item Group", filters={"parent_item_group": g}, pluck="name")

    items = frappe.get_all(
        "Item",
        filters={"disabled": 0, "is_sales_item": 1,
                 "item_group": ("in", list(set(groups)))},
        fields=["item_code", "item_name", "item_group", "image",
                "standard_rate", "description"],
        order_by="item_group asc, item_name asc",
    )
    out = {}
    for it in items:
        out.setdefault(it.item_group, []).append(it)
    return out


@frappe.whitelist(methods=["POST"])
def place_order(items):
    """items: JSON list of {"item_code": ..., "qty": ...}. Priced from the
    Item master server-side — the client never sets prices."""
    from duckies.wallet.si_hooks import make_wallet_invoice

    customer = get_customer_for_user()
    if isinstance(items, str):
        items = json.loads(items)
    if not items:
        frappe.throw(_("Your order is empty."))

    clean = []
    for it in items:
        code, qty = it.get("item_code"), flt(it.get("qty") or 1)
        if qty <= 0:
            continue
        if not frappe.db.exists("Item", {"name": code, "disabled": 0,
                                         "is_sales_item": 1}):
            frappe.throw(_("Item {0} is not available.").format(code))
        clean.append({"item_code": code, "qty": qty})  # rate from price list
    if not clean:
        frappe.throw(_("Your order is empty."))

    si = make_wallet_invoice(customer, clean, remarks=_("Web order"))
    return {
        "invoice": si.name,
        "total": si.grand_total,
        "balance": get_balance(customer),
        "message": _("Order placed! It will be with you shortly."),
    }
