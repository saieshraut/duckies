# Copyright (c) 2026, Duckie's Sports Cafe

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class RechargeRequest(Document):
    def validate(self):
        if flt(self.amount) <= 0:
            frappe.throw(_("Amount must be greater than zero."))

        if self.channel == "Offline":
            s = frappe.get_cached_doc("Duckies Settings")
            if flt(self.amount) < flt(s.min_recharge_amount):
                frappe.throw(_("Minimum recharge is {0}.").format(
                    s.min_recharge_amount))
            # Section 269ST: no single cash receipt of >= 2,00,000.
            if self.payment_mode == "Cash" and flt(self.amount) >= 200000:
                frappe.throw(_(
                    "Single cash receipts of Rs 2,00,000 or more are barred "
                    "under Section 269ST. Use UPI / bank transfer, or split "
                    "the amount."))
            # Default the deposit account from settings if staff left it blank.
            if not self.payment_account:
                self.payment_account = s.deposit_account

    def before_submit(self):
        # Online requests are settled by the Razorpay webhook, not by submit.
        if self.channel == "Online" and self.status != "Paid":
            frappe.throw(_(
                "Online recharges are completed via the payment gateway, not "
                "by submitting this form."))

    def on_submit(self):
        """Submitting an Offline request loads the wallet + posts accounting."""
        if self.channel != "Offline":
            return
        if self.status == "Paid":
            return  # already settled (e.g. amended)

        from duckies.wallet.api import apply_recharge, get_buckets

        remark = _("Front-desk recharge ({0}").format(self.payment_mode or "Offline")
        if self.payment_reference:
            remark += f" / ref {self.payment_reference}"
        remark += ")"

        # Translate the staff's offer choice into the apply_recharge param:
        #   Auto (best offer) -> None  (auto-pick)
        #   Choose offer      -> the selected offer name
        #   No bonus          -> "none" (suppress)
        if self.offer_mode == "No bonus":
            offer_arg = "none"
        elif self.offer_mode == "Choose offer":
            offer_arg = self.offer
        else:
            offer_arg = None

        cash_txn, bonus_txn, bonus, je_name = apply_recharge(
            self.customer, flt(self.amount),
            "Recharge Request", self.name, remark,
            deposit_account=self.payment_account,
            offer=offer_arg,
        )

        self.db_set("status", "Paid")
        self.db_set("bonus_amount", bonus)
        self.db_set("wallet_transaction", cash_txn.name)
        if bonus_txn:
            self.db_set("bonus_wallet_transaction", bonus_txn.name)
        if je_name:
            self.db_set("journal_entry", je_name)

        cash, bns = get_buckets(self.customer)
        frappe.msgprint(
            _("Wallet loaded. New balance: {0} (cash {1} + bonus {2}).").format(
                frappe.format_value(cash + bns, {"fieldtype": "Currency"}),
                frappe.format_value(cash, {"fieldtype": "Currency"}),
                frappe.format_value(bns, {"fieldtype": "Currency"})),
            alert=True, indicator="green")

    def on_cancel(self):
        frappe.throw(_(
            "A completed recharge cannot be cancelled — it would leave the "
            "customer's wallet out of balance. Use a Wallet Refund Request "
            "or a manual Adjustment instead."))


@frappe.whitelist()
def get_bonus_preview(amount, offer_mode="Auto (best offer)", offer=None):
    """Live preview of the bonus for the current amount + offer choice.
    Returns {bonus, offer_label}."""
    from duckies.wallet.api import resolve_offer
    amount = flt(amount)
    if offer_mode == "No bonus":
        arg = "none"
    elif offer_mode == "Choose offer":
        arg = offer
    else:
        arg = None
    bonus, label = resolve_offer(arg, amount)
    return {"bonus": bonus, "offer_label": label}
