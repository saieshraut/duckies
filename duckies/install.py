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
                "label": "Wallet Balance (Total)",
                "read_only": 1, "no_copy": 1,
                "insert_after": "custom_wallet_section",
            },
            {
                "fieldname": "custom_wallet_cash",
                "fieldtype": "Currency",
                "label": "Cash Balance (Refundable)",
                "read_only": 1, "no_copy": 1,
                "insert_after": "custom_wallet_balance",
            },
            {
                "fieldname": "custom_wallet_bonus",
                "fieldtype": "Currency",
                "label": "Bonus Balance (Non-refundable)",
                "read_only": 1, "no_copy": 1,
                "insert_after": "custom_wallet_cash",
            },
            {
                "fieldname": "custom_wallet_cb",
                "fieldtype": "Column Break",
                "insert_after": "custom_wallet_bonus",
            },
            {
                "fieldname": "custom_wallet_last_activity",
                "fieldtype": "Datetime",
                "label": "Wallet Last Activity",
                "read_only": 1, "no_copy": 1,
                "insert_after": "custom_wallet_cb",
            },
            {
                "fieldname": "custom_user",
                "fieldtype": "Link", "options": "User",
                "label": "Portal User",
                "unique": 1, "no_copy": 1,
                "insert_after": "custom_wallet_last_activity",
            },
            # ---- DPDP Act 2023 consent & data-protection ----
            {
                "fieldname": "custom_dpdp_section",
                "fieldtype": "Section Break",
                "label": "Consent & Data Protection",
                "insert_after": "custom_user",
            },
            {
                "fieldname": "custom_consent_given",
                "fieldtype": "Check",
                "label": "Consent to T&Cs and Privacy Notice",
                "insert_after": "custom_dpdp_section",
            },
            {
                "fieldname": "custom_consent_on",
                "fieldtype": "Datetime",
                "label": "Consent Given On",
                "read_only": 1,
                "insert_after": "custom_consent_given",
            },
            {
                "fieldname": "custom_consent_version",
                "fieldtype": "Data",
                "label": "Consent Version",
                "read_only": 1,
                "insert_after": "custom_consent_on",
            },
            {
                "fieldname": "custom_dpdp_cb",
                "fieldtype": "Column Break",
                "insert_after": "custom_consent_version",
            },
            # ---- Minor / family-member model ----
            # Minors do NOT get their own login. A parent account holds the
            # wallet; minors are represented as guardian-linked profiles, which
            # sidesteps DPDP verifiable-parental-consent obligations.
            {
                "fieldname": "custom_is_minor",
                "fieldtype": "Check",
                "label": "Is Minor (managed by guardian)",
                "insert_after": "custom_dpdp_cb",
            },
            {
                "fieldname": "custom_guardian",
                "fieldtype": "Link", "options": "Customer",
                "label": "Guardian Account",
                "depends_on": "custom_is_minor",
                "insert_after": "custom_is_minor",
            },
        ],
        # Age-gating for alcohol at POS / web (Goa drinking age 18)
        "Item": [
            {
                "fieldname": "custom_age_restricted",
                "fieldtype": "Check",
                "label": "Age Restricted (18+)",
                "insert_after": "is_sales_item",
            },
            {
                "fieldname": "custom_is_liquor",
                "fieldtype": "Check",
                "label": "Liquor (VAT, separate bill series)",
                "insert_after": "custom_age_restricted",
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
    breakage = make_account("Wallet Breakage Income",
                            "Indirect Income", "Income")

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
    s.breakage_income_account = breakage
    if not s.deposit_account:
        s.deposit_account = frappe.db.get_value(
            "Account", {"company": company, "account_type": "Bank",
                        "is_group": 0})
    s.flags.ignore_permissions = True
    s.save()

    setup_tax_templates(company)
    frappe.db.commit()
    return {"wallet_liability_account": liability,
            "promo_expense_account": promo,
            "breakage_income_account": breakage,
            "deposit_account": s.deposit_account}


@frappe.whitelist()
def setup_tax_templates(company: str):
    """Create Item Tax Templates for the three redemption rates and attach
    them to the right Item Groups.

      * Events / amusement           -> 18% GST (SAC 9996)
      * Food & non-alcoholic         -> 5% GST (restaurant, no ITC)
      * Alcohol                      -> OUTSIDE GST; Goa VAT (rate set by CA)

    Rates below are defaults for convenience — CONFIRM every rate and account
    head with your CA before go-live. VAT rate is left at 0 for you to set.
    """
    frappe.only_for("System Manager")
    abbr = frappe.db.get_value("Company", company, "abbr")

    def tax_account(name, rate, root_type="Liability", parent_label="Duties and Taxes"):
        full = f"{name} - {abbr}"
        if frappe.db.exists("Account", full):
            return full
        parent = frappe.db.get_value("Account", {
            "company": company, "is_group": 1,
            "account_name": ("like", f"%{parent_label}%")})
        if not parent:
            parent = frappe.db.get_value("Account", {
                "company": company, "root_type": root_type, "is_group": 1})
        acc = frappe.get_doc({
            "doctype": "Account", "account_name": name, "company": company,
            "parent_account": parent, "root_type": root_type,
            "account_type": "Tax", "tax_rate": rate, "is_group": 0})
        acc.flags.ignore_permissions = True
        acc.insert()
        return acc.name

    def item_tax_template(title, entries, gst_treatment="Taxable"):
        full = f"{title} - {abbr}"
        if frappe.db.exists("Item Tax Template", {"title": title, "company": company}):
            return full
        payload = {
            "doctype": "Item Tax Template", "title": title, "company": company,
            "taxes": [{"tax_type": acc, "tax_rate": rate} for acc, rate in entries],
        }
        # india_compliance adds a GST Treatment field. Alcohol is outside GST
        # (Non-GST) and must carry NO tax rows — a 0% taxable row is rejected.
        if frappe.get_meta("Item Tax Template").has_field("gst_treatment"):
            payload["gst_treatment"] = gst_treatment
            if gst_treatment != "Taxable":
                payload["taxes"] = []
        doc = frappe.get_doc(payload)
        doc.flags.ignore_permissions = True
        doc.insert()
        return doc.name

    # GST accounts (split CGST/SGST for intra-state Goa)
    templates = {}
    for label, rate in (("18", 18.0), ("5", 5.0)):
        cgst = tax_account(f"Output CGST {float(rate)/2:g}%", rate / 2)
        sgst = tax_account(f"Output SGST {float(rate)/2:g}%", rate / 2)
        templates[label] = item_tax_template(
            f"GST {label}%", [(cgst, rate / 2), (sgst, rate / 2)])

    # Liquor is Non-GST (outside GST). No GST tax rows. Goa VAT is handled
    # separately as a Sales Taxes and Charges template, NOT here — GST-tax
    # accounts and VAT don't mix on one Item Tax Template under india_compliance.
    templates["liquor"] = item_tax_template(
        "Liquor (Non-GST)", [], gst_treatment="Non-GST")

    # Attach templates to item groups
    def attach(group, template):
        if not frappe.db.exists("Item Group", group):
            return
        ig = frappe.get_doc("Item Group", group)
        if not any(t.item_tax_template == template for t in ig.taxes):
            ig.append("taxes", {"item_tax_template": template})
            ig.flags.ignore_permissions = True
            ig.save()

    attach("Events", templates["18"])
    attach("Food", templates["5"])
    attach("Non-Alcoholic", templates["5"])
    attach("Cocktails", templates["liquor"])
    attach("Spirits", templates["liquor"])
    frappe.db.commit()
    return {"templates": templates,
            "note": "Liquor is set Non-GST. Goa VAT is a separate Sales Taxes "
                    "and Charges Template applied at billing — set it up with "
                    "your CA. Confirm all GST rates too."}
