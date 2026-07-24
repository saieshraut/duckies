// Copyright (c) 2026, Duckie's Sports Cafe
frappe.ui.form.on("Recharge Request", {
    onload(frm) {
        if (frm.is_new() && !frm.doc.channel) {
            frm.set_value("channel", "Offline");
        }
        if (frm.is_new() && !frm.doc.offer_mode) {
            frm.set_value("offer_mode", "Auto (best offer)");
        }
    },

    customer(frm) {
        if (!frm.doc.customer) return;
        frappe.db.get_value("Customer", frm.doc.customer,
            ["custom_wallet_balance", "custom_wallet_cash", "custom_wallet_bonus"])
            .then(r => {
                const d = r.message || {};
                frm.dashboard.set_headline(
                    __("Current wallet balance: {0} (cash {1} + bonus {2})", [
                        format_currency(d.custom_wallet_balance || 0),
                        format_currency(d.custom_wallet_cash || 0),
                        format_currency(d.custom_wallet_bonus || 0),
                    ])
                );
            });
    },

    amount(frm) { preview_bonus(frm); },
    offer_mode(frm) { preview_bonus(frm); },
    offer(frm) { preview_bonus(frm); },

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

function preview_bonus(frm) {
    if (frm.doc.docstatus !== 0) return;
    if (!frm.doc.amount || frm.doc.channel !== "Offline") {
        frm.set_value("preview_bonus", 0);
        return;
    }
    frappe.call({
        method: "duckies.duckies.doctype.recharge_request.recharge_request.get_bonus_preview",
        args: {
            amount: frm.doc.amount,
            offer_mode: frm.doc.offer_mode || "Auto (best offer)",
            offer: frm.doc.offer,
        },
        callback(r) {
            if (!r.message) return;
            frm.set_value("preview_bonus", r.message.bonus || 0);
            if (r.message.bonus > 0 && r.message.offer_label) {
                frm.set_df_property("preview_bonus", "description",
                    __("Offer: {0}", [r.message.offer_label]));
                frm.refresh_field("preview_bonus");
            }
        },
    });
}
