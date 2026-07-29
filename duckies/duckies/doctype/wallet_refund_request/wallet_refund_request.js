// Copyright (c) 2026, Duckie's Sports Cafe
frappe.ui.form.on("Wallet Refund Request", {
    customer(frm) {
        if (!frm.doc.customer || frm.doc.docstatus !== 0) return;
        frappe.db.get_value("Customer", frm.doc.customer, "custom_wallet_cash")
            .then(r => {
                frm.set_value("amount", flt(r.message && r.message.custom_wallet_cash));
            });
    },

    refresh(frm) {
        const can_process = frm.doc.docstatus === 1
            && ["Requested", "Approved"].includes(frm.doc.status)
            && frappe.user.has_role(["System Manager", "Cafe Manager"]);

        if (can_process) {
            frm.add_custom_button(__("Process Refund"), () => {
                frappe.confirm(
                    __("Refund {0} to {1}? This debits the wallet{2} and cannot be undone.", [
                        format_currency(frm.doc.amount),
                        frm.doc.customer,
                        frm.doc.refund_to === "Original Payment Source"
                            ? __(" and reverses it via Razorpay")
                            : "",
                    ]),
                    () => {
                        frappe.call({
                            method: "duckies.payments.razorpay.process_refund",
                            args: { refund_request: frm.doc.name },
                            freeze: true,
                            freeze_message: __("Processing refund..."),
                            callback(r) {
                                if (!r.exc) {
                                    frappe.show_alert({
                                        message: __("Refund processed."),
                                        indicator: "green",
                                    });
                                    frm.reload_doc();
                                }
                            },
                        });
                    }
                );
            }).addClass("btn-primary");
        }

        if (frm.doc.status === "Processed") {
            frm.dashboard.set_headline(
                __("✓ Refunded {0} to {1}", [
                    format_currency(frm.doc.amount),
                    frm.doc.customer,
                ])
            );
        }
    },
});
