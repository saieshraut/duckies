// Copyright (c) 2026, Duckie's Sports Cafe
frappe.ui.form.on("Duckies Settings", {
    refresh(frm) {
        if (!frappe.user.has_role("System Manager")) return;

        frm.add_custom_button(__("Reset Wallet & Booking Data"), () => {
            frappe.confirm(
                __(
                    "This will permanently delete <b>all</b> Wallet Transactions, " +
                    "Wallet Refund Requests, Recharge Requests and Event Bookings, " +
                    "and reset every customer's wallet balance to zero. " +
                    "This cannot be undone.<br><br>Are you sure you want to continue?"
                ),
                () => {
                    frappe.call({
                        method:
                            "duckies.duckies.doctype.duckies_settings.duckies_settings.reset_transactional_data",
                        freeze: true,
                        freeze_message: __("Resetting data..."),
                        callback(r) {
                            if (!r.exc) {
                                frappe.show_alert(
                                    { message: r.message, indicator: "green" },
                                    10
                                );
                            }
                        },
                    });
                }
            );
        }, __("Actions"));
    },
});
