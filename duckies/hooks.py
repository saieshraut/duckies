app_name = "duckies"
app_title = "Duckies"
app_publisher = "Duckie's Sports Cafe"
app_description = (
    "Prepaid wallet, spaces, events & bookings for Duckie's Sports Cafe"
)
app_email = "dev@duckies.example"
app_license = "MIT"

required_apps = ["erpnext"]

# ---------------------------------------------------------------- install
after_install = "duckies.install.after_install"

# --------------------------------------------------------------- doc hooks
doc_events = {
    "Sales Invoice": {
        "validate": "duckies.wallet.si_hooks.validate_wallet_payment",
        "on_submit": "duckies.wallet.si_hooks.debit_wallet_on_submit",
        "on_cancel": "duckies.wallet.si_hooks.refund_wallet_on_cancel",
    },
}

# --------------------------------------------------------------- scheduler
scheduler_events = {
    "daily": [
        "duckies.events.tasks.generate_upcoming_events",
    ],
    "hourly": [
        "duckies.events.tasks.update_event_statuses",
    ],
}
