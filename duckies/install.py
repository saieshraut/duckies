# Copyright (c) 2026, Duckie's Sports Cafe
"""Install-time setup + one post-install helper for company accounts.

after_install handles everything company-independent. Accounts are
company-specific, so after creating your Company in the ERPNext setup
wizard, run once from `bench console` (or call via API as Administrator):

    from duckies.install import setup_accounts
    setup_accounts("Duckie's Sports Cafe Pvt Ltd")
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

MENU_ROOT = "From the Kitchen & Bar"
MENU_CHILDREN = ["Food", "Cocktails", "Spirits", "Non-Alcoholic"]

SPACES = [
    ("The Dizzy Duck", "Bar at Duckie's",
     "Our signature bar serving classic cocktails, Goan-inspired sips, and "
     "small-batch spirits in a vintage tavern setting.", 0),
    ("The Pickle Jar", "Pickleball Court at Duckie's",
     "Goa's most playful pickleball court. Open court play, leagues, and "
     "clinics for all levels.", 1),
    ("Platform 13", "Mahjong • Rummy • Bridge",
     "Eight tables, endless games. Reserve a table for mahjong, rummy, "
     "bridge, or your favourite board game.", 1),
    ("The Groove Room", "Every Vibe. Every Day.",
     "Live jazz, stand-up, improv, art films, and sports screenings by "
     "night. Yoga, dance, and workshops by day. Capacity 50.", 1),
    ("Grassholes", "Croquet • Yoga • Community",
     "Open-air lawn for croquet, putting, lawn bowling, and outdoor "
     "sunrise yoga.", 1),
]


def after_install():
    make_custom_fields()
    make_roles()
    make_mode_of_payment()
    make_item_groups()
    seed_spaces()
    set_default_settings()
    frappe.db.commit()


def make_custom_fields():
    create_custom_fields({
        "Customer": [
            {
                "fieldname": "custom_wallet_section",
                "fieldtype": "Section Break",
                "label": "Duckie's Wallet",
                "insert_after": "customer_details",
            },
            {
                "fieldname": "custom_wallet_balance",
                "fieldtype": "Currency",
                "label": "Wallet Balance",
                "read_only": 1,
                "no_copy": 1,
                "insert_after": "custom_wallet_section",
            },
            {
                "fieldname": "custom_user",
                "fieldtype": "Link",
                "options": "User",
                "label": "Portal User",
                "unique": 1,
                "no_copy": 1,
                "insert_after": "custom_wallet_balance",
            },
        ],
    }, ignore_validate=True)


def make_roles():
    if not frappe.db.exists("Role", "Cafe Manager"):
        frappe.get_doc({
            "doctype": "Role", "role_name": "Cafe Manager",
            "desk_access": 1,
        }).insert(ignore_permissions=True)


def make_mode_of_payment():
    if not frappe.db.exists("Mode of Payment", "Wallet"):
        frappe.get_doc({
            "doctype": "Mode of Payment",
            "mode_of_payment": "Wallet",
            "type": "General",
            "enabled": 1,
        }).insert(ignore_permissions=True)


def make_item_groups():
    def ensure(name, parent):
        if not frappe.db.exists("Item Group", name):
            frappe.get_doc({
                "doctype": "Item Group", "item_group_name": name,
                "parent_item_group": parent,
                "is_group": 1 if name == MENU_ROOT else 0,
            }).insert(ignore_permissions=True)

    ensure(MENU_ROOT, "All Item Groups")
    for child in MENU_CHILDREN:
        ensure(child, MENU_ROOT)
    ensure("Events", "All Item Groups")


def seed_spaces():
    for name, tagline, desc, bookable in SPACES:
        if not frappe.db.exists("Cafe Space", name):
            frappe.get_doc({
                "doctype": "Cafe Space",
                "space_name": name,
                "tagline": tagline,
                "description": desc,
                "is_bookable": bookable,
                "is_active": 1,
            }).insert(ignore_permissions=True)


def set_default_settings():
    s = frappe.get_doc("Duckies Settings")
    if not s.menu_root_item_group:
        s.menu_root_item_group = MENU_ROOT
    if not s.min_recharge_amount:
        s.min_recharge_amount = 100
    if not s.cancellation_cutoff_hours:
        s.cancellation_cutoff_hours = 4
    s.enforce_wallet_only = 1
    s.flags.ignore_permissions = True
    s.save()


# --------------------------------------------------------------------------
# Run once after the ERPNext setup wizard has created your Company
# --------------------------------------------------------------------------

@frappe.whitelist()
def setup_accounts(company: str):
    """Creates the wallet liability + promo expense accounts, wires the
    Wallet mode of payment to the liability account, and fills Duckies
    Settings."""
    frappe.only_for("System Manager")
    abbr = frappe.db.get_value("Company", company, "abbr")

    def make_account(account_name, parent_label, root_type):
        existing = frappe.db.exists(
            "Account", {"account_name": account_name, "company": company})
        if existing:
            return existing
        parent = frappe.db.get_value("Account", {
            "company": company, "root_type": root_type, "is_group": 1,
            "account_name": ("like", f"%{parent_label}%"),
        })
        if not parent:  # fall back to the root group
            parent = frappe.db.get_value("Account", {
                "company": company, "root_type": root_type, "is_group": 1,
                "parent_account": ("in", ("", None)),
            })
        acc = frappe.get_doc({
            "doctype": "Account", "account_name": account_name,
            "company": company, "parent_account": parent,
            "root_type": root_type, "is_group": 0,
        })
        acc.flags.ignore_permissions = True
        acc.insert()
        return acc.name

    liability = make_account("Customer Wallet Liability",
                             "Current Liabilities", "Liability")
    promo = make_account("Wallet Promotional Expense",
                         "Indirect Expenses", "Expense")

    # Point the Wallet mode of payment at the liability account
    mop = frappe.get_doc("Mode of Payment", "Wallet")
    if not any(a.company == company for a in mop.accounts):
        mop.append("accounts", {"company": company,
                                "default_account": liability})
        mop.flags.ignore_permissions = True
        mop.save()

    s = frappe.get_doc("Duckies Settings")
    s.company = company
    s.wallet_liability_account = liability
    s.promo_expense_account = promo
    if not s.deposit_account:
        s.deposit_account = frappe.db.get_value(
            "Account", {"company": company, "account_type": "Bank",
                        "is_group": 0})
    s.flags.ignore_permissions = True
    s.save()
    frappe.db.commit()
    return {"wallet_liability_account": liability,
            "promo_expense_account": promo,
            "deposit_account": s.deposit_account}
