# Copyright (c) 2026, Duckie's Sports Cafe
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class WalletTransaction(Document):
    def before_insert(self):
        from frappe.utils import now_datetime
        if not self.posting_datetime:
            self.posting_datetime = now_datetime()

    def on_cancel(self):
        frappe.throw(_("Wallet Transactions are an immutable ledger and cannot be cancelled. "
                       "Post an Adjustment or Refund instead."))
