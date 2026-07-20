# Copyright (c) 2026, Duckie's Sports Cafe
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class RechargeOffer(Document):
    def validate(self):
        if self.bonus_type == "Fixed Amount" and not self.bonus_amount:
            frappe.throw(_("Set a Bonus Amount for a Fixed Amount offer."))
        if self.bonus_type == "Percent" and not self.bonus_percent:
            frappe.throw(_("Set a Bonus Percent for a Percent offer."))
