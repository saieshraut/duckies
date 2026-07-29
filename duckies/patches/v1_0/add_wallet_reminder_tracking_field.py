# Copyright (c) 2026, Duckie's Sports Cafe
"""Backfill the custom_wallet_reminders_sent field on existing installs.

Needed for the expiry-reminder catch-up fix: send_expiry_reminders() now
records which day-thresholds it has already notified per expiry cycle, so a
missed scheduler run doesn't silently skip a customer's reminder."""

from duckies.install import make_custom_fields


def execute():
    make_custom_fields()
