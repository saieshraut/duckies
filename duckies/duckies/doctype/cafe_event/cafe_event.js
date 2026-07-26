// Copyright (c) 2026, Duckie's Sports Cafe
frappe.ui.form.on("Cafe Event", {
    refresh(frm) {
        if (frm.is_new()) return;
        if (frm.doc.status !== "Upcoming") return;

        // Staff action: book this event for a walk-in customer.
        frm.add_custom_button(__("Book for Customer"), () => {
            const d = new frappe.ui.Dialog({
                title: __("Book {0}", [frm.doc.event_name]),
                fields: [
                    {
                        fieldname: "customer", fieldtype: "Link",
                        options: "Customer", label: __("Customer"), reqd: 1,
                    },
                    {
                        fieldname: "seats", fieldtype: "Int",
                        label: __("Seats"), default: 1, reqd: 1,
                    },
                    { fieldname: "bal_html", fieldtype: "HTML" },
                ],
                primary_action_label: __("Book & Charge Wallet"),
                primary_action(values) {
                    frappe.call({
                        method: "duckies.events.api.staff_book_event",
                        args: {
                            customer: values.customer,
                            event: frm.doc.name,
                            seats: values.seats,
                        },
                        freeze: true,
                        freeze_message: __("Booking..."),
                        callback(r) {
                            if (!r.message) return;
                            frappe.show_alert({
                                message: r.message.message + " " +
                                    __("Wallet balance: {0}",
                                       [format_currency(r.message.balance)]),
                                indicator: "green",
                            }, 7);
                            d.hide();
                            frm.reload_doc();
                        },
                    });
                },
            });

            // Show the customer's wallet balance when one is picked.
            d.fields_dict.customer.df.onchange = () => {
                const cust = d.get_value("customer");
                if (!cust) return;
                frappe.db.get_value("Customer", cust,
                    ["custom_wallet_balance", "custom_wallet_cash", "custom_wallet_bonus"])
                    .then((res) => {
                        const v = res.message || {};
                        const need = (frm.doc.price || 0) * (d.get_value("seats") || 1);
                        const short = (v.custom_wallet_balance || 0) < need;
                        d.fields_dict.bal_html.$wrapper.html(
                            `<div class="text-muted" style="margin-top:6px">
                               Wallet: <b>${format_currency(v.custom_wallet_balance || 0)}</b>
                               (cash ${format_currency(v.custom_wallet_cash || 0)} +
                               bonus ${format_currency(v.custom_wallet_bonus || 0)})
                               ${short ? '<br><span style="color:#c0392b">Insufficient for this booking — recharge first.</span>' : ''}
                             </div>`);
                    });
            };
        }, __("Actions"));
    },
});
