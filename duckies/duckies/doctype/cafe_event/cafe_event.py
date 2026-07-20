# Copyright (c) 2026, Duckie's Sports Cafe
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class CafeEvent(Document):
    def validate(self):
        if self.capacity is not None and (self.seats_booked or 0) > self.capacity:
            frappe.throw(_("Seats booked cannot exceed capacity."))

    def before_save(self):
        from duckies.events.tasks import get_or_create_event_item
        if not self.item:
            self.item = get_or_create_event_item(self.event_name)

    @property
    def seats_left(self):
        return max(0, (self.capacity or 0) - (self.seats_booked or 0))
