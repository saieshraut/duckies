# Duckie's — India Compliance Guide (v2)

> This documents *why* the app is built the way it is, mapped to Indian law as
> of mid-2026. It is a briefing for your CA and lawyer, **not** legal or tax
> advice. Confirm every rate, account head and threshold with them before
> go-live. Regulations change — re-check the RBI PPI Master Direction and GST
> rate notifications near launch.

## 1. RBI — Closed System PPI (no licence needed)

The wallet is a **Closed System Prepaid Payment Instrument**: usable only to
buy Duckie's own goods and services, from the single legal entity that issues
it, with **no cash withdrawal** and **no third-party / peer transfers**. On
that basis it is exempt from RBI authorisation.

Hard product rules that keep the exemption valid (all enforced in code or by
the absence of any contrary code path):

| Rule | Where enforced |
|---|---|
| No cash withdrawal from the wallet | No withdrawal endpoint exists. Refunds go to the original payment source only. |
| No third-party or wallet-to-wallet transfer | No transfer endpoint exists. |
| One issuing entity redeems everything | All invoices post to the single company in Duckies Settings. |
| Bonus never becomes cash | Bonus bucket is non-refundable; `request_refund`/`process_refund` cap at the cash bucket. |

The draft **MD-PPIs, 2026** preserves the closed-system exemption for any
issuer that is **not a marketplace**. A cafe selling its own services is not a
marketplace — but never let outside vendors sell through the wallet, or the
exemption is lost.

**No KYC** is required for closed PPIs — name, mobile, email is enough. We do
**not** collect Aadhaar/PAN (avoids needless DPDP exposure). Offline top-ups
must stay on UPI: `offline_recharge` blocks single receipts ≥ ₹2,00,000
(Income-tax **Section 269ST**).

## 2. GST / VAT — taxed at redemption, not at load

Per **CBIC Circular 243/37/2024** and the **Finance Act 2025**, a wallet load
is a *money* transaction — **not** a supply — so **no GST on recharge or
bonus**. GST/VAT applies only when something is actually bought:

| Revenue stream | Treatment | Config |
|---|---|---|
| Events, courts, tables, workshops (amusement) | 18% GST, SAC 9996 | `GST 18%` template on `Events` group |
| Restaurant food & non-alcoholic drinks | 5% GST (no ITC) | `GST 5%` template on `Food`, `Non-Alcoholic` |
| **Alcohol** | **Outside GST** — Goa VAT | `Goa VAT - Liquor` template on `Cocktails`, `Spirits`; set rate per your CA |
| Recharge / bonus | Not a supply — no GST | Journal Entry only |
| Expiry / breakage | Not a supply — no GST (income only) | `expire_lapsed_wallets` posts JE to Breakage Income |

`setup_tax_templates()` creates these and attaches them to the item groups.
The VAT rate ships at **0** deliberately — set it once your excise/VAT
position is confirmed.

**Stay out of the 40% "sin" slab.** Rummy / bridge / mahjong must be **table
bookings only** — never wallet-funded stakes or cash prizes. Any prize pool or
stake turns the space into betting/gaming (40% GST + Goa gambling licensing +
likely loss of the closed-PPI exemption). Keep it in the T&Cs and staff SOP.

Set tax templates **inclusive** so the menu price equals the wallet debit.
Liquor may need a **separate bill series** (`liquor_invoice_naming_series` in
Duckies Settings) — confirm Goa's requirement with your CA.

## 3. Wallet expiry, breakage & refunds (Consumer Protection Act)

- **Validity**: `wallet_validity_months` (default 12) from **last activity** —
  each recharge or spend resets the clock (more defensible than from load
  date).
- **Notice**: reminders at `expiry_reminder_days` (default `30,7`) before
  expiry, logged as sent — your CCPA defence.
- **Breakage** on expiry is written back to income via Journal Entry; **no
  GST** (CBIC 243/37/2024).
- **Refunds**: unused **cash** is refundable to the original source
  (`request_refund` → staff `process_refund` → Razorpay refund + reversal JE).
  **Bonus is never refundable** and the code enforces the cap.

## 4. DPDP Act 2023 (rules notified Nov 2025)

- **Consent** is mandatory at signup — `register` refuses without it and
  stamps `custom_consent_on` + `custom_consent_version`.
- **Children**: minors get **no** login or wallet. A parent account holds the
  wallet; minors are guardian-linked profiles (`add_family_member`,
  `custom_is_minor` + `custom_guardian`). This mirrors how mall game-zone
  cards work and sidesteps DPDP verifiable-parental-consent machinery.
- **Erasure**: `delete_my_account` anonymises personal data but **retains
  financial documents** (tax law requires 6–8 yr retention; DPDP allows
  retention required by law) and disables the login.
- **Data minimisation**: we collect only name, mobile, email, and transaction
  history. No DOB, address, or ID documents.

## 5. Licences your client needs (Goa) — not app work

Excise (bar), FSSAI (kitchen), Trade Licence + Shops & Establishments, Fire
NOC (Groove Room seats 50 → assembly norms), **PPL + IPRS** (recorded &
live music), **commercial screening/viewing rights** for sports and film
nights, and local entertainment/sound permits. Several take months — start
early. Age-gate alcohol: the web app blocks `custom_age_restricted` items
(`place_order`), and the bar must verify age in person (drinking age 18 in
Goa).

## 6. Audit trail

Wallet Transactions are an immutable, submitted ledger — they can't be
cancelled. Corrections are separate **Adjustment** entries, so history is
never rewritten. Wallet balances reconcile to the **Customer Wallet
Liability** account at all times: recharge credits it, every spend (via Sales
Invoice paid by the Wallet mode of payment) debits it, refunds and breakage
clear it.
