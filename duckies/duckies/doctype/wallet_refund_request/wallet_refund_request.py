# Copyright (c) 2026, Duckie's Sports Cafe

import frappe
from frappe import _
from frappe.model.document import Document


class WalletRefundRequest(Document):
    def validate(self):
        from frappe.utils import flt
        from duckies.wallet.api import get_buckets
        if self.docstatus == 0 and self.customer:
            cash, _bonus = get_buckets(self.customer)
            if flt(self.amount) > cash + 0.005:
                frappe.throw(_("Refund cannot exceed the refundable cash "
                               "balance ({0}). Bonus credit is not "
                               "refundable.").format(cash))

    def on_submit(self):
        # Submitting = approval. The actual money movement + Razorpay call is
        # done explicitly by staff via process_refund so failures are visible.
        pass
