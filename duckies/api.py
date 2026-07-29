# Copyright (c) 2026, Duckie's Sports Cafe
"""Customer-facing API for the web app.

Portal users get NO direct DocType permissions — they interact only through
these endpoints, and the Customer is always resolved server-side from the
session. That way nobody can hit the generic REST API and edit their own
wallet balance.

All endpoints: POST /api/method/duckies.api.<function>
(GET also works for the read-only ones.)
"""

import frappe
from frappe import _
from frappe.utils import (
    cint, flt, get_datetime, getdate, now_datetime, today, validate_email_address,
)

from duckies.wallet.api import (
    get_balance,
    get_buckets,
    get_customer_for_user,
    qr_code_for_customer,
)


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
    mobile = (mobile or "").strip()
    if not (full_name or "").strip():
        frappe.throw(_("Please tell us your name."))
    if not mobile:
        frappe.throw(_("Please provide a mobile number."))
    if len(password or "") < 8:
        frappe.throw(_("Password must be at least 8 characters."))
    if not cint(consent):
        frappe.throw(_("Please accept the Terms & Conditions and Privacy "
                       "Notice to create an account."))
    if frappe.db.exists("User", email):
        frappe.throw(_("An account with this email already exists. Please log in."))
    # One wallet per phone number: prevents the same person opening repeat
    # accounts to re-claim first-recharge bonus offers, and catches
    # accidental duplicate signups. Family members (add_family_member) don't
    # carry their own mobile_no, so they never collide with this check.
    if frappe.db.exists("Customer", {"mobile_no": mobile}):
        frappe.throw(_("An account with this mobile number already exists. "
                       "Please log in, or contact the front desk if this "
                       "isn't you."))

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
        "qr_code": qr_code_for_customer(c.name),
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
           to_date: str | None = None, limit: int = 50, featured=None):
    # Hard upper bound on rows, independent of the caller-supplied limit, so a
    # bad/large request can never load an unbounded result set.
    page_len = min(max(cint(limit) or 50, 1), 100)

    filters = {
        "status": "Upcoming",
        "date": (">=", getdate(from_date) if from_date else getdate(today())),
    }
    if space:
        filters["space"] = space
    if featured:
        filters["is_featured"] = 1
    if to_date:
        filters["date"] = ("between", [filters["date"][1], getdate(to_date)])

    rows = frappe.get_all(
        "Cafe Event", filters=filters,
        fields=["name", "event_name", "space", "date", "start_time",
                "end_time", "price", "capacity", "seats_booked", "image",
                "description", "is_featured", "is_cancellable",
                "cancellation_cutoff_hours", "refund_type", "refund_percentage",
                "refund_flat_amount"],
        order_by="date asc, start_time asc",
        limit_page_length=page_len,
    )
    from duckies.duckies.cancellation import get_cutoff_hours

    for r in rows:
        r["seats_left"] = max(0, cint(r.capacity) - cint(r.seats_booked))
        # Resolve the effective cutoff (event override, else the global
        # default) so the app never has to know about Duckies Settings.
        r["cancellation_cutoff_hours"] = get_cutoff_hours(r)
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
    cancelled = _cancel(customer, booking)
    refund_amount = flt(getattr(cancelled, "refund_amount", 0))
    message = (
        _("Booking cancelled. {0} refunded to your wallet.").format(
            frappe.utils.fmt_money(refund_amount, currency="INR"))
        if refund_amount > 0
        else _("Booking cancelled. This event's policy has no refund.")
    )
    return {"balance": get_balance(customer), "refund_amount": refund_amount,
            "message": message}


@frappe.whitelist()
def my_bookings(limit: int = 20, start: int = 0):
    from duckies.duckies.cancellation import compute_refund_amount, get_cutoff_hours

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
            ["event_name", "space", "date", "start_time", "is_cancellable",
             "cancellation_cutoff_hours", "refund_type", "refund_percentage",
             "refund_flat_amount"],
            as_dict=True)
        if not ev:
            continue
        r.update({
            "event_name": ev.event_name, "space": ev.space, "date": ev.date,
            "start_time": ev.start_time,
        })
        cutoff_hours = get_cutoff_hours(ev)
        start_dt = get_datetime(f"{ev.date} {ev.start_time}")
        hours_to_go = (start_dt - now_datetime()).total_seconds() / 3600.0
        r["is_cancellable"] = bool(ev.is_cancellable)
        r["cutoff_passed"] = hours_to_go < cutoff_hours
        r["expected_refund"] = compute_refund_amount(ev, r.amount_paid, r.seats)
    return rows


# --------------------------------------------------------------------------
# Menu & food orders
# --------------------------------------------------------------------------

@frappe.whitelist(allow_guest=True)
def menu():
    """Return the menu as ordered sections, each with its items and the set of
    sub-category filters present.

    Shape:
      {
        "sections": [
          {"name": "Small Plates",
           "categories": ["Veg", "Non-Veg"],
           "items": [{item_code, item_name, standard_rate, image,
                      description, category, age_restricted}, ...]},
          {"name": "Cocktails", "categories": [...], "items": [...]}
        ]
      }
    The app renders one tab per section and "All / <category>" filter chips.
    """
    root = (frappe.get_cached_doc("Duckies Settings").menu_root_item_group
            or "From the Kitchen & Bar")

    # Preferred section order (falls back to whatever groups exist under root).
    preferred = ["Small Plates", "Cocktails"]
    child_groups = frappe.get_all(
        "Item Group", filters={"parent_item_group": root}, pluck="name")
    sections_order = [g for g in preferred if g in child_groups] + \
        [g for g in child_groups if g not in preferred]

    price_list = frappe.db.get_single_value("Selling Settings", "selling_price_list")

    sections = []
    for group in sections_order:
        items = frappe.get_all(
            "Item",
            filters={"disabled": 0, "is_sales_item": 1, "item_group": group},
            fields=["item_code", "item_name", "image", "standard_rate",
                    "description", "custom_menu_category as category",
                    "custom_age_restricted as age_restricted"],
            order_by="custom_menu_category asc, item_name asc",
        )
        if not items:
            continue

        # standard_rate on Item is only ever set at creation time (it's hidden
        # on the form afterwards), so the real, editable rate lives in Item
        # Price against the default selling price list. Prefer that.
        prices = {}
        if price_list:
            prices = {
                p.item_code: p.price_list_rate
                for p in frappe.get_all(
                    "Item Price",
                    filters={
                        "item_code": ["in", [it.item_code for it in items]],
                        "price_list": price_list,
                        "selling": 1,
                    },
                    fields=["item_code", "price_list_rate"],
                )
            }
        for it in items:
            it.standard_rate = flt(prices.get(it.item_code) or it.standard_rate)
        # Distinct categories present, in a stable order.
        seen, categories = set(), []
        for it in items:
            c = it.get("category")
            if c and c not in seen:
                seen.add(c)
                categories.append(c)
        sections.append({
            "name": group,
            "categories": categories,
            "items": items,
        })

    return {"sections": sections}


@frappe.whitelist(methods=["POST"])
def place_order(items):
    """DISABLED — the app menu is view-only. Ordering happens in person at the
    counter/table and is billed there against the wallet. This endpoint is kept
    (returning an error) so any stale client can't place orders.

    The former online-order implementation (wallet debit + background
    Sales Invoice posting) lived here; it's gone from HEAD but preserved in
    git history if in-app ordering is re-enabled later — see the project's
    version control log for `_place_order_disabled`."""
    frappe.throw(
        _("Ordering from the app isn't available. Please order at the counter "
          "or your table — it'll be billed to your Duckie's wallet."),
        title=_("View-only menu"))


# --------------------------------------------------------------------------
# Refunds & family members
# --------------------------------------------------------------------------

@frappe.whitelist(methods=["POST"])
def request_refund(amount, reason=None):
    """Customer asks to refund unused CASH balance to source. Creates a
    Requested refund for staff to approve + process. Bonus is never
    refundable, so the ask is capped at the cash bucket — and any live Bonus
    is forfeited when the refund is processed (see
    payments.razorpay.process_refund / wallet.api.forfeit_bonus), since a
    customer can't cash out real money and keep promotional credit funded by
    the same recharge."""
    customer = get_customer_for_user()
    s = frappe.get_cached_doc("Duckies Settings")
    if not s.allow_self_refund:
        frappe.throw(_("Please raise refund requests at the front desk."))
    cash, bonus = get_buckets(customer)
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
    message = _("Refund requested. We'll process it to your original "
                "payment method shortly.")
    if bonus > 0:
        message = _(
            "Refund requested. We'll process it to your original payment "
            "method shortly. Note: your bonus balance of {0} will be "
            "forfeited when this refund is processed, as promotional "
            "credit can't be cashed out.").format(
                frappe.format_value(bonus, {"fieldtype": "Currency"}))
    return {"refund_request": req.name, "bonus_at_risk": bonus,
            "message": message}


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
    DPDP permits retention required by law. The login is disabled.

    Blocked while the wallet still holds a balance: disabling the login
    without disposing of the balance first would strand the customer's money
    behind an account they can no longer access themselves. They must spend
    it down or request a cash refund (request_refund) before deleting."""
    customer = get_customer_for_user()
    balance = get_balance(customer)
    if balance > 0.005:
        frappe.throw(
            _("You still have {0} in your wallet. Please spend it or "
              "request a refund of your cash balance before closing your "
              "account — closing the account disables login, and staff "
              "will need to help you recover funds afterwards.").format(
                  frappe.format_value(balance, {"fieldtype": "Currency"})),
            title=_("Wallet balance not zero"),
        )
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
