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

from duckies.wallet.api import get_balance, get_buckets, get_customer_for_user


# --------------------------------------------------------------------------
# Auth
# --------------------------------------------------------------------------

CONSENT_VERSION = "2026-01"


@frappe.whitelist(allow_guest=True, methods=["POST"])
def register(full_name: str, email: str, mobile: str, password: str,
             consent: int = 0):
    """Create a Website User + linked Customer, then log them in.

    DPDP Act 2023: explicit, recorded consent is mandatory. We refuse
    registration without it and stamp the version + timestamp. Minors do not
    self-register (see add_family_member) — this account is treated as an
    adult data-principal giving their own consent.
    """
    email = (email or "").strip().lower()
    validate_email_address(email, throw=True)
    if not (full_name or "").strip():
        frappe.throw(_("Please tell us your name."))
    if len(password or "") < 8:
        frappe.throw(_("Password must be at least 8 characters."))
    if not cint(consent):
        frappe.throw(_("Please accept the Terms & Conditions and Privacy "
                       "Notice to create an account."))
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
        "custom_consent_given": 1,
        "custom_consent_on": frappe.utils.now_datetime(),
        "custom_consent_version": CONSENT_VERSION,
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
         "custom_wallet_balance", "custom_wallet_cash", "custom_wallet_bonus",
         "custom_wallet_last_activity"],
        as_dict=True,
    )
    from duckies.wallet.expiry import expiry_date_for
    exp = (expiry_date_for(c.custom_wallet_last_activity)
           if c.custom_wallet_last_activity else None)
    return {
        "customer": c.name,
        "name": c.customer_name,
        "mobile": c.mobile_no,
        "email": c.email_id,
        "wallet_balance": flt(c.custom_wallet_balance),
        "cash_balance": flt(c.custom_wallet_cash),
        "bonus_balance": flt(c.custom_wallet_bonus),
        "wallet_expiry": exp,
    }


# --------------------------------------------------------------------------
# Wallet
# --------------------------------------------------------------------------

@frappe.whitelist()
def balance():
    customer = get_customer_for_user()
    cash, bonus = get_buckets(customer)
    return {"balance": cash + bonus, "cash_balance": cash,
            "bonus_balance": bonus}


@frappe.whitelist()
def transactions(limit: int = 20, start: int = 0):
    customer = get_customer_for_user()
    rows = frappe.get_all(
        "Wallet Transaction",
        filters={"customer": customer, "docstatus": 1},
        fields=["name", "posting_datetime", "transaction_type", "direction",
                "bucket", "amount", "balance_after", "remarks"],
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
    Item master server-side — the client never sets prices.

    Age-restricted (alcohol) items are blocked from the web app entirely:
    Goa's drinking age is 18 and online self-declaration is not a lawful age
    check, so liquor must be served at the bar with in-person verification.
    """
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
        meta = frappe.db.get_value(
            "Item", {"name": code, "disabled": 0, "is_sales_item": 1},
            ["name", "custom_age_restricted"], as_dict=True)
        if not meta:
            frappe.throw(_("Item {0} is not available.").format(code))
        if meta.custom_age_restricted:
            frappe.throw(_("Alcohol can't be ordered through the app. Please "
                           "order at The Dizzy Duck bar — age verification is "
                           "done in person."), title=_("18+ / In-person only"))
        clean.append({"item_code": code, "qty": qty})  # rate from price list
    if not clean:
        frappe.throw(_("Your order is empty."))

    si = make_wallet_invoice(customer, clean, remarks=_("Web order"))
    cash, bonus = get_buckets(customer)
    return {
        "invoice": si.name,
        "total": si.grand_total,
        "balance": cash + bonus,
        "cash_balance": cash,
        "bonus_balance": bonus,
        "message": _("Order placed! It will be with you shortly."),
    }


# --------------------------------------------------------------------------
# Refunds & family members
# --------------------------------------------------------------------------

@frappe.whitelist(methods=["POST"])
def request_refund(amount, reason=None):
    """Customer asks to refund unused CASH balance to source. Creates a
    Requested refund for staff to approve + process. Bonus is never
    refundable, so the ask is capped at the cash bucket."""
    customer = get_customer_for_user()
    s = frappe.get_cached_doc("Duckies Settings")
    if not s.allow_self_refund:
        frappe.throw(_("Please raise refund requests at the front desk."))
    cash, _bonus = get_buckets(customer)
    amount = flt(amount)
    if amount <= 0 or amount > cash + 0.005:
        frappe.throw(_("You can refund up to your refundable cash balance "
                       "({0}). Bonus credit is not refundable.").format(cash))

    # Link the most recent successful online recharge for source reversal.
    last_recharge = frappe.db.get_value(
        "Recharge Request",
        {"customer": customer, "status": "Paid", "channel": "Online"},
        "name", order_by="creation desc")

    req = frappe.get_doc({
        "doctype": "Wallet Refund Request", "customer": customer,
        "amount": amount, "reason": reason, "status": "Requested",
        "refund_to": "Original Payment Source",
        "original_recharge": last_recharge,
    })
    req.flags.ignore_permissions = True
    req.insert()
    return {"refund_request": req.name,
            "message": _("Refund requested. We'll process it to your original "
                         "payment method shortly.")}


@frappe.whitelist(methods=["POST"])
def add_family_member(full_name, is_minor: int = 0):
    """Add a guardian-linked profile (e.g. a child) under the logged-in adult
    account. Minors never get their own login or wallet — the guardian's
    wallet pays, which keeps us clear of DPDP verifiable-parental-consent
    machinery for children's accounts."""
    guardian = get_customer_for_user()
    if not (full_name or "").strip():
        frappe.throw(_("Please provide the family member's name."))
    member = frappe.get_doc({
        "doctype": "Customer",
        "customer_name": f"{full_name.strip()} (via {guardian})",
        "customer_type": "Individual",
        "customer_group": frappe.db.get_single_value(
            "Selling Settings", "customer_group") or "Individual",
        "territory": frappe.db.get_single_value(
            "Selling Settings", "territory") or "All Territories",
        "custom_is_minor": cint(is_minor),
        "custom_guardian": guardian,
    })
    member.flags.ignore_permissions = True
    member.insert()
    return {"member": member.name,
            "message": _("Family member added. Their play is paid from your "
                         "wallet.")}


@frappe.whitelist(methods=["POST"])
def delete_my_account():
    """DPDP right to erasure. We anonymise personal data but RETAIN financial
    documents (invoices, ledger) — tax law requires 6-8 year retention, and
    DPDP permits retention required by law. The login is disabled."""
    customer = get_customer_for_user()
    user = frappe.db.get_value("Customer", customer, "custom_user")
    frappe.db.set_value("Customer", customer, {
        "customer_name": f"Deleted Customer {customer}",
        "mobile_no": None, "email_id": None, "custom_user": None,
    })
    if user:
        frappe.db.set_value("User", user, {"enabled": 0})
    return {"message": _("Your account has been closed and personal details "
                         "removed. Transaction records are retained only as "
                         "required by tax law.")}
