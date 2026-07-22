# Duckies — Prepaid Sports Cafe app for Frappe / ERPNext

Custom Frappe app powering **Duckie's Sports Cafe**: a strictly prepaid,
wallet-only cafe with bookable spaces, recurring events, food & drinks via
ERPNext POS, recharge offers, and a JSON API ready for a customer web app.

Built for **Frappe / ERPNext v15/v16**.

> **India compliance (v2):** the wallet is a closed-system PPI with a
> cash/bonus bucket split, wallet expiry + breakage, refund-to-source, GST/VAT
> config, and DPDP consent/erasure. The legal basis for each design choice is
> in **[COMPLIANCE.md](./COMPLIANCE.md)** — read it with your CA and lawyer;
> confirm all rates and thresholds before go-live.

---

## What's inside

| DocType | Purpose |
|---|---|
| **Wallet Transaction** | Immutable, submittable ledger. Every credit/debit. Balance cached on Customer. |
| **Cafe Space** | The Dizzy Duck, The Pickle Jar, Platform 13, The Groove Room, Grassholes (seeded on install). |
| **Event Template** | Recurring event definition (one-time / daily / weekly / monthly). Auto-creates a service Item for invoicing. |
| **Cafe Event** | A single bookable occurrence, materialised ~30 days ahead by the scheduler. |
| **Event Booking** | Customer booking with seats, linked Sales Invoice. |
| **Recharge Offer** | "Load ₹2000 get ₹2500" style offers (fixed or percent bonus). |
| **Recharge Request** | One row per recharge attempt (online Razorpay or offline front-desk). |
| **Duckies Settings** | Accounts, Razorpay keys, wallet rules, menu root. |

Money design (agree this with your CA):

- Recharge → **Dr Bank / Cr Customer Wallet Liability** (money loaded is a liability, not revenue)
- Bonus → **Dr Promotional Expense / Cr Wallet Liability**
- Every spend (food, drink, event seat) → ordinary **Sales Invoice** paid via Mode of Payment **"Wallet"** (mapped to the liability account), so revenue + GST flow through ERPNext untouched.
- The Sales Invoice `on_submit` hook debits the wallet ledger; `on_cancel` refunds it. **One spending path for everything.**
- `enforce_wallet_only` blocks any POS invoice paid by cash/card — "no cash, no cards" is enforced by the system.

---

## 1. Installation

```bash
cd frappe-bench
# copy/clone this folder into apps/duckies, then:
bench get-app ./apps/duckies        # or: bench get-app <your git url>
bench --site yoursite.local install-app duckies
bench --site yoursite.local migrate
bench --site yoursite.local clear-cache
```

`after_install` automatically creates:
- Custom fields on Customer: `custom_wallet_balance`, `custom_user`
- Role **Cafe Manager**
- Mode of Payment **Wallet**
- Item Groups: `From the Kitchen & Bar` → Food / Cocktails / Spirits / Non-Alcoholic, plus `Events`
- The five Cafe Spaces
- Sane defaults in Duckies Settings

## 2. One-time setup after the ERPNext wizard

1. Complete the ERPNext **setup wizard** (creates your Company, chart of accounts, tax templates).
2. Wire the accounts. This creates the Wallet Liability, Promo Expense and Breakage Income accounts, links the Wallet mode of payment, and — via `setup_tax_templates`, which it now calls automatically — creates the 18% / 5% GST and Goa VAT item-tax templates and attaches them to the right item groups:

```bash
bench --site yoursite.local console
>>> from duckies.install import setup_accounts
>>> setup_accounts("Your Company Name")
```

   The Goa VAT (liquor) template is created at **rate 0** on purpose — set the real rate once your excise/VAT position is confirmed, then re-run `setup_tax_templates("Your Company Name")` or edit the template in the desk.

3. Open **Duckies Settings** in the desk and confirm/set:
   - `deposit_account` — the bank account Razorpay settles into
   - `breakage_income_account` — auto-set, confirm it
   - `wallet_validity_months` (default 12), `expiry_reminder_days` (default `30,7`), `allow_self_refund`
   - `liquor_invoice_naming_series` if your CA wants a separate VAT bill series
   - Razorpay `key_id`, `key_secret`, `webhook_secret`
4. In the **Razorpay dashboard** add a webhook:
   - URL: `https://<your-site>/api/method/duckies.payments.razorpay.webhook`
   - Events: `payment.captured` (optionally `payment.failed`)
   - Secret: identical to the one in Duckies Settings
5. Ensure the scheduler is running (`bench --site yoursite.local enable-scheduler`).
6. Optional but recommended for the bar counter: create a **POS Profile**
   with **Wallet as the only payment method** and use ERPNext POS (or POS
   Awesome) for offline orders.

## 3. Admin workflows (all in the ERPNext desk — no custom UI needed)

- **Events**: create an *Event Template* (e.g. "Sunrise Yoga", space Grassholes, Weekly, Sat+Sun, 06:30, ₹400, capacity 20). Occurrences appear immediately in *Cafe Event* and keep generating nightly. Edit or cancel any single occurrence freely.
- **Menu**: normal ERPNext *Item* management under `From the Kitchen & Bar`. Add images and `standard_rate` — the web API serves them as the menu.
- **Offers**: create *Recharge Offer* rows, e.g. min ₹2000 → Fixed Amount ₹500. Best applicable offer is applied automatically on every recharge.
- **Front-desk recharge** (customer pays your UPI QR / you allow cash for *loading only*): call `duckies.wallet.api.offline_recharge` (Cafe Manager role) or build a tiny desk page around it.
- **Corrections**: `duckies.wallet.api.manual_adjustment` (System Manager, reason mandatory).
- **Give staff the Cafe Manager role** — it has full rights on all Duckies doctypes.

## 4. Customer web app API

Base: `POST https://<site>/api/method/duckies.api.<fn>` (cookie session auth).
Responses are wrapped by Frappe as `{"message": <return value>}`.

| Endpoint | Auth | Purpose |
|---|---|---|
| `duckies.api.register` | guest | `full_name, email, mobile, password, consent` → creates User+Customer, logs in. **`consent` (1) is mandatory** (DPDP) |
| `/api/method/login` | guest | Frappe built-in: `usr`, `pwd` |
| `/api/method/logout` | session | Frappe built-in |
| `duckies.api.get_profile` | session | name, mobile, wallet balance |
| `duckies.api.balance` | session | wallet balance |
| `duckies.api.transactions` | session | ledger history (`limit`, `start`) |
| `duckies.api.active_offers` | session | current recharge offers |
| `duckies.api.spaces` | guest | the five spaces |
| `duckies.api.events` | guest | upcoming events (`space`, `from_date`, `to_date`) with `seats_left` |
| `duckies.api.book_event` | session | `event`, `seats` → invoice + wallet debit + booking |
| `duckies.api.cancel_booking` | session | `booking` → refund if before cutoff |
| `duckies.api.my_bookings` | session | booking history |
| `duckies.api.menu` | guest | items grouped by Item Group |
| `duckies.api.place_order` | session | `items=[{item_code, qty}]` → wallet-paid invoice. Blocks age-restricted (alcohol) items |
| `duckies.api.request_refund` | session | `amount, reason` → refund request for unused **cash** (bonus is non-refundable) |
| `duckies.api.add_family_member` | session | `full_name, is_minor` → guardian-linked profile paid from your wallet |
| `duckies.api.delete_my_account` | session | DPDP erasure: anonymises personal data, keeps financial records |
| `duckies.payments.razorpay.process_refund` | staff | `refund_request` → wallet debit + Razorpay refund-to-source + reversal JE |
| `duckies.payments.razorpay.create_recharge_order` | session | `amount` → Razorpay order for Checkout |

`balance`, `get_profile`, `transactions` and the order/booking responses now return `cash_balance` and `bonus_balance` separately (plus `wallet_expiry` on the profile), so the app can show the two buckets and the expiry date.

### Frontend recharge flow (vanilla JS, works the same in Vue/React)

```html
<script src="https://checkout.razorpay.com/v1/checkout.js"></script>
<script>
async function api(method, body) {
  const r = await fetch(`/api/method/${method}`, {
    method: "POST",
    headers: { "Content-Type": "application/json",
               "X-Frappe-CSRF-Token": frappe?.csrf_token ?? "" },
    credentials: "include",
    body: JSON.stringify(body ?? {}),
  });
  const data = await r.json();
  if (!r.ok) throw data;
  return data.message;
}

async function rechargeWallet(amountInRupees) {
  const order = await api("duckies.payments.razorpay.create_recharge_order",
                          { amount: amountInRupees });
  new Razorpay({
    key: order.key_id,
    order_id: order.order_id,
    amount: order.amount,          // paise, from server
    currency: order.currency,
    name: order.name,
    description: order.description,
    handler: () => {
      // Payment window succeeded — but the wallet is credited only when the
      // signed WEBHOOK arrives. Poll the balance for a few seconds:
      pollBalance();
    },
  }).open();
}

async function pollBalance(tries = 10) {
  for (let i = 0; i < tries; i++) {
    const { balance } = await api("duckies.api.balance");
    updateBalanceUI(balance);
    await new Promise(res => setTimeout(res, 1500));
  }
}
</script>
```

### Booking an event

```js
await api("duckies.api.book_event", { event: "EVT-00042", seats: 2 });
// throws a readable error if the event is full or balance is insufficient
```

### Recommended frontend stack

A Vue 3 SPA using [frappe-ui](https://github.com/frappe/frappe-ui) mounted at
`/cafe`, shipped as a PWA (customers will use it standing at the bar). All
state lives behind the endpoints above; portal users need **zero** DocType
permissions.

## 5. Testing checklist

```bash
bench --site yoursite.local console
```

```python
import frappe
from duckies.api import register  # or create test data directly:

# 1. Registration
frappe.set_user("Administrator")
from duckies.wallet.api import apply_recharge, get_balance, create_wallet_txn

cust = "CUST-0001"          # any test customer with custom_user set

# 2. Recharge + offer
frappe.get_doc({"doctype": "Recharge Offer", "offer_name": "Load 2000 Get 2500",
                "min_recharge_amount": 2000, "bonus_type": "Fixed Amount",
                "bonus_amount": 500, "is_active": 1}).insert()
apply_recharge(cust, 2000)          # balance should now be 2500
print(get_balance(cust))

# 3. Event flow
tpl = frappe.get_doc({"doctype": "Event Template", "event_name": "Sunrise Yoga",
    "space": "Grassholes", "price": 400, "capacity": 20,
    "recurrence": "Daily", "start_date": frappe.utils.today(),
    "start_time": "06:30:00", "duration_mins": 60, "is_active": 1}).insert()
ev = frappe.get_all("Cafe Event", filters={"template": tpl.name}, limit=1)[0]

from duckies.events.api import book_event
bkg = book_event(cust, ev.name, 2)   # debits 800, seats_booked = 2
print(get_balance(cust))             # 1700

# 4. Overbooking + insufficient balance should both throw cleanly
```

Then test Razorpay end-to-end in **test mode** with the webhook pointed at a
tunnel (e.g. `ngrok`) before going live.

## 6. Known deliberate choices / next steps

- **Loyalty**: enable ERPNext's Loyalty Program on Sales Invoices (all spends already are invoices). Add a "convert points → wallet Bonus" endpoint when ready.
- **Refund policy**: full refund before the cutoff hour; change `cancel_booking` for partial-refund rules.
- **GST on events vs F&B**: attach the right Item Tax Templates to the Event item group and menu groups.
- **RBI note**: this is a *closed-system* PPI (spendable only at the issuing merchant, no cash-out, no transfers) — exempt from RBI authorisation. Keep it that way in your T&Cs; confirm the refund-to-source policy with your lawyer/CA.
- **Wallet Transactions are uncancellable** by design; correct mistakes with Adjustment entries so the audit trail stays intact.
