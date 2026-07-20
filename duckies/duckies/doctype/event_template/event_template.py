# Copyright (c) 2026, Duckie's Sports Cafe
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class EventTemplate(Document):
    def validate(self):
        if self.recurrence == "Weekly" and not any(
            self.get(d) for d in
            ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
        ):
            frappe.throw(_("Weekly recurrence needs at least one weekday ticked."))
        if self.recurrence == "Monthly" and not self.day_of_month:
            frappe.throw(_("Monthly recurrence needs a day of month."))
        if self.end_date and self.start_date and self.end_date < self.start_date:
            frappe.throw(_("End Date cannot be before Start Date."))

    def before_save(self):
        from duckies.events.tasks import get_or_create_event_item
        if not self.item:
            self.item = get_or_create_event_item(self.event_name)

    def on_update(self):
        # Materialise occurrences immediately so admins see them without
        # waiting for the nightly scheduler run.
        if self.is_active:
            from duckies.events.tasks import generate_for_template
            generate_for_template(self.name)
