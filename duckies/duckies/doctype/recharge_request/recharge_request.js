// Copyright (c) 2026, Duckie's Sports Cafe
frappe.ui.form.on("Recharge Request", {
    onload(frm) {
        if (frm.is_new() && !frm.doc.channel) {
            frm.set_value("channel", "Offline");
        }
    },

    customer(frm) {
        if (!frm.doc.customer) return;
        frappe.db.get_value("Customer", frm.doc.customer,
            ["custom_wallet_balance", "custom_wallet_cash", "custom_wallet_bonus"])
            .then(r => {
                const d = r.message || {};
                frm.dashboard.clear_headline();
                frm.dashboard.set_headline(
                    __("Current wallet balance: {0} (cash {1} + bonus {2})", [
                        format_currency(d.custom_wallet_balance || 0),
                        format_currency(d.custom_wallet_cash || 0),
                        format_currency(d.custom_wallet_bonus || 0),
                    ])
                );
            });
    },

    refresh(frm) {
        if (frm.doc.docstatus === 1 && frm.doc.status === "Paid") {
            frm.dashboard.set_headline(
                __("✓ Wallet loaded with {0}{1}", [
                    format_currency(frm.doc.amount),
                    frm.doc.bonus_amount
                        ? __(" + {0} bonus", [format_currency(frm.doc.bonus_amount)])
                        : "",
                ])
            );
        }
    },
});
