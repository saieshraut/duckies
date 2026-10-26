# Copyright (c) 2026, Duckie's Sports Cafe
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, flt, get_datetime, getdate, today

# Fields the desk UI is allowed to change after an event has been created.
# Everything else is frozen once the event exists — see validate_immutable().
EDITABLE_AFTER_CREATION = {"price", "status", "capacity"}

# Fieldtypes that carry no data of their own and should never be treated as
# a "change" (layout only).
LAYOUT_FIELDTYPES = {"Section Break", "Column Break", "Tab Break"}


class CafeEvent(Document):
    def validate(self):
        if self.is_new():
            self.validate_event_date()
            self.validate_event_times()
        else:
            self.validate_immutable()

        # Re-checked whenever a doc becomes (or starts out) non-Cancelled —
        # not just at creation. Status is editable after creation, so
        # cancelling one event, creating a new one in its slot, then
        # un-cancelling the first would otherwise double-book the space
        # without ever tripping this check.
        if self.status != "Cancelled" and (self.is_new() or self.has_value_changed("status")):
            self.validate_no_space_overlap()

        self.validate_price()

        if self.capacity is not None and (self.seats_booked or 0) > self.capacity:
            frappe.throw(_("Seats booked cannot exceed capacity."))

        from duckies.duckies.cancellation import validate_cancellation_policy
        validate_cancellation_policy(self)

    def validate_event_date(self):
        """Events must be created at least 1 day ahead — no back-dated or
        same-day events. Blank is left to the standard mandatory-field
        check, which runs right after validate()."""
        if not self.date:
            return
        if getdate(self.date) < add_days(getdate(today()), 1):
            frappe.throw(_(
                "Events cannot be back-dated and must be created at least "
                "1 day before the event date."
            ))

    def validate_event_times(self):
        if not (self.start_time and self.end_time):
            return
        if self.end_time <= self.start_time:
            frappe.throw(_("End Time must be after Start Time."))

    def validate_no_space_overlap(self):
        if not (self.space and self.date and self.start_time):
            return

        # Lock the space for the rest of this transaction so two concurrent
        # inserts/status-changes for the same space can't both read "no
        # conflict" before either commits (TOCTOU race) — mirrors
        # events.api._lock_event, but here nothing may exist yet to lock, so
        # lock the (always-existing) Cafe Space row instead.
        frappe.db.sql(
            "SELECT name FROM `tabCafe Space` WHERE name=%s FOR UPDATE",
            (self.space,),
        )

        start = get_datetime(f"{self.date} {self.start_time}")
        end = get_datetime(f"{self.date} {self.end_time or self.start_time}")

        for other in frappe.get_all(
            "Cafe Event",
            filters={
                "space": self.space,
                "date": self.date,
                "status": ("!=", "Cancelled"),
                "name": ("!=", self.name or ""),
            },
            fields=["name", "start_time", "end_time"],
        ):
            other_start = get_datetime(f"{self.date} {other.start_time}")
            other_end = get_datetime(f"{self.date} {other.end_time or other.start_time}")
            if start < other_end and other_start < end:
                frappe.throw(_(
                    "{0} overlaps with existing event {1} ({2}–{3}) in the same space."
                ).format(self.space, other.name, other.start_time, other.end_time or other.start_time))

    def validate_price(self):
        if flt(self.price) < 0:
            frappe.throw(_("Price cannot be negative."))

    def validate_immutable(self):
        """Once created, an event is locked except for Price, Status and
        Capacity (rate corrections, cancelling/rolling status, and seat-count
        corrections are legitimate day-2 operations; everything else —
        date, time, space, template, etc. — must not change)."""
        before = self.get_doc_before_save()
        if not before:
            return

        changed = [
            df.fieldname for df in self.meta.fields
            if df.fieldtype not in LAYOUT_FIELDTYPES
            and df.fieldname not in EDITABLE_AFTER_CREATION
            and self.has_value_changed(df.fieldname)
        ]
        if changed:
            frappe.throw(_(
                "This event cannot be modified after creation — only "
                "Price, Status and Capacity can be changed. Field(s) not "
                "allowed to change: {0}"
            ).format(", ".join(changed)))

    def before_save(self):
        from duckies.events.tasks import get_or_create_event_item
        if not self.item:
            self.item = get_or_create_event_item(self.event_name)

    def on_update(self):
        # Admin cancelled the whole event: fully refund every confirmed
        # booking, regardless of the event's own (partial) refund policy.
        # is_new() is excluded since a brand-new event created straight into
        # Cancelled has no bookings to refund yet.
        if not self.is_new() and self.status == "Cancelled" and self.has_value_changed("status"):
            from duckies.events.api import cancel_event_bookings
            cancel_event_bookings(self.name)

    @property
    def seats_left(self):
        return max(0, (self.capacity or 0) - (self.seats_booked or 0))
