# Copyright (c) 2026, Duckie's Sports Cafe
"""Recurrence engine: materialises Cafe Event occurrences from templates.

Runs nightly (see hooks.py) and also immediately when a template is saved,
keeping ~30 days of bookable occurrences ahead. Admins can freely edit or
cancel a single occurrence without touching the series.
"""

import frappe
from frappe.utils import (
    add_days, add_to_date, cint, flt, get_datetime, getdate, now_datetime, today,
)

HORIZON_DAYS = 30
WEEKDAY_FIELDS = ["monday", "tuesday", "wednesday", "thursday",
                  "friday", "saturday", "sunday"]

EVENT_ITEM_GROUP = "Events"


def get_or_create_event_item(event_name: str) -> str:
    """Every bookable event maps to a non-stock service Item so invoicing,
    GST and per-space revenue reports come free from ERPNext."""
    item_code = f"EVT - {event_name}"[:140]
    if frappe.db.exists("Item", item_code):
        return item_code

    _ensure_item_group()
    item = frappe.get_doc({
        "doctype": "Item",
        "item_code": item_code,
        "item_name": event_name[:140],
        "item_group": EVENT_ITEM_GROUP,
        "is_stock_item": 0,
        "is_sales_item": 1,
        "is_purchase_item": 0,
        "include_item_in_manufacturing": 0,
        "stock_uom": "Nos",
    })
    item.flags.ignore_permissions = True
    item.insert(ignore_mandatory=True)
    return item.name


def _ensure_item_group():
    if not frappe.db.exists("Item Group", EVENT_ITEM_GROUP):
        frappe.get_doc({
            "doctype": "Item Group",
            "item_group_name": EVENT_ITEM_GROUP,
            "parent_item_group": "All Item Groups",
            "is_group": 0,
        }).insert(ignore_permissions=True)


def _dates_for_template(t, horizon_end) -> list:
    start = getdate(t.start_date)
    window_start = max(start, getdate(today()))
    window_end = getdate(horizon_end)
    if t.end_date:
        window_end = min(window_end, getdate(t.end_date))

    if t.recurrence == "One-time":
        return [start] if window_start <= start <= window_end else []

    dates, d = [], window_start
    while d <= window_end:
        if t.recurrence == "Daily":
            dates.append(d)
        elif t.recurrence == "Weekly":
            if t.get(WEEKDAY_FIELDS[d.weekday()]):
                dates.append(d)
        elif t.recurrence == "Monthly":
            if d.day == cint(t.day_of_month):
                dates.append(d)
        d = add_days(d, 1)
    return dates


def _end_time(start_time, duration_mins):
    base = get_datetime(f"{today()} {start_time}")
    return add_to_date(base, minutes=cint(duration_mins) or 60).time()


def generate_for_template(template_name: str):
    t = frappe.get_doc("Event Template", template_name)
    if not t.is_active:
        return 0
    horizon_end = add_days(today(), HORIZON_DAYS)
    created = 0
    for d in _dates_for_template(t, horizon_end):
        if frappe.db.exists("Cafe Event", {
            "template": t.name, "date": d, "start_time": t.start_time,
        }):
            continue
        frappe.get_doc({
            "doctype": "Cafe Event",
            "event_name": t.event_name,
            "template": t.name,
            "space": t.space,
            "description": t.description,
            "image": t.image,
            "date": d,
            "start_time": t.start_time,
            "end_time": _end_time(t.start_time, t.duration_mins),
            "price": flt(t.price),
            "capacity": cint(t.capacity),
            "status": "Upcoming",
            "item": t.item,
        }).insert(ignore_permissions=True)
        created += 1
    return created


def generate_upcoming_events():
    """Nightly scheduler entry point."""
    for name in frappe.get_all("Event Template", filters={"is_active": 1},
                               pluck="name"):
        try:
            generate_for_template(name)
        except Exception:
            frappe.log_error(
                title=f"Event generation failed: {name}",
                message=frappe.get_traceback(),
            )
    frappe.db.commit()


def update_event_statuses():
    """Hourly: roll Upcoming → Ongoing → Completed based on the clock."""
    now = now_datetime()
    for ev in frappe.get_all(
        "Cafe Event",
        filters={"status": ("in", ["Upcoming", "Ongoing"])},
        fields=["name", "date", "start_time", "end_time", "status"],
    ):
        start = get_datetime(f"{ev.date} {ev.start_time}")
        end = get_datetime(f"{ev.date} {ev.end_time or ev.start_time}")
        new_status = None
        if end < now:
            new_status = "Completed"
        elif start <= now <= end and ev.status == "Upcoming":
            new_status = "Ongoing"
        if new_status and new_status != ev.status:
            frappe.db.set_value("Cafe Event", ev.name, "status", new_status,
                                update_modified=False)
    frappe.db.commit()
