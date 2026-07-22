# Copyright (c) 2026, Duckie's Sports Cafe
"""Smoke test as a single callable — run in ONE clean process with:

    bench --site <site> execute duckies.smoke_test.run

(Do NOT pipe this into `console`; the interactive REPL mangles multi-line
blocks. `bench execute` runs it as one function, which is what we want.)
"""
import frappe
from frappe.utils import today, now_datetime
from duckies.wallet.api import apply_recharge, get_buckets


def _show(cust, label):
    cash, bonus = get_buckets(cust)
    print(f"  [{label}] cash={cash}  bonus={bonus}  total={cash + bonus}")


def _ledger(cust):
    for r in frappe.get_all("Wallet Transaction",
            filters={"customer": cust, "docstatus": 1},
            fields=["transaction_type", "direction", "bucket", "amount", "balance_after"],
            order_by="creation asc"):
        print(f"   {r.transaction_type:10} {r.direction:6} {r.bucket:5} "
              f"{r.amount:8} -> {r.balance_after}")


def run():
    stamp = now_datetime().strftime("%H%M%S")

    print("\n=== 0. Create test customer ===")
    cust = frappe.get_doc({
        "doctype": "Customer", "customer_name": f"Smoke Test {stamp}",
        "customer_type": "Individual",
        "customer_group": frappe.db.get_single_value("Selling Settings", "customer_group") or "Individual",
        "territory": frappe.db.get_single_value("Selling Settings", "territory") or "All Territories",
        "email_id": f"smoketest_{stamp}@duckies.test",
    }).insert(ignore_permissions=True)
    print("  customer:", cust.name)

    print("\n=== 1. Test offer: load 2000 get 500 ===")
    if not frappe.db.exists("Recharge Offer", "SMOKE Load2000Get500"):
        frappe.get_doc({
            "doctype": "Recharge Offer", "offer_name": "SMOKE Load2000Get500",
            "min_recharge_amount": 2000, "bonus_type": "Fixed Amount",
            "bonus_amount": 500, "is_active": 1,
        }).insert(ignore_permissions=True)
        print("  created offer")
    else:
        print("  offer exists")

    print("\n=== 2. Recharge 2000 (expect cash=2000, bonus=500) ===")
    apply_recharge(cust.name, 2000, remarks="smoke test recharge")
    _show(cust.name, "after recharge")

    # print("\n=== 3. Create a test event today ===")
    # space = frappe.get_all("Cafe Space", limit=1, pluck="name")[0]
    # from duckies.events.tasks import get_or_create_event_item
    # item = get_or_create_event_item("Smoke Test Session")
    # print("  event item:", item)
    # ev = frappe.get_doc({
    #     "doctype": "Cafe Event", "event_name": "Smoke Test Session",
    #     "space": space, "date": today(), "start_time": "23:59:00",
    #     "price": 300, "capacity": 10, "status": "Upcoming", "item": item,
    # }).insert(ignore_permissions=True)
    # print("  event:", ev.name)

    # print("\n=== 4. Book 2 seats (expect 600: bonus 500 then cash 100) ===")
    # from duckies.events.api import book_event
    # bkg = book_event(cust.name, ev.name, 2)
    # _show(cust.name, "after booking")
    # print("  booking:", bkg.name, "| invoice:", bkg.sales_invoice)

    # print("\n=== 5. Ledger after booking ===")
    # _ledger(cust.name)

    # print("\n=== 6. Cancel booking (expect 600 refunded to same buckets) ===")
    # from duckies.events.api import cancel_booking
    # s = frappe.get_doc("Duckies Settings")
    # s.cancellation_cutoff_hours = 0
    # s.flags.ignore_permissions = True
    # s.save()
    # cancel_booking(cust.name, bkg.name)
    # _show(cust.name, "after cancel+refund")

    # print("\n=== 7. Final ledger ===")
    # _ledger(cust.name)

    # cash, bonus = get_buckets(cust.name)
    # ok = (cash == 2000 and bonus == 500)
    # print("\n=== RESULT ===")
    # print(f"  buckets restored to cash=2000 bonus=500 ? "
    #       f"{'PASS' if ok else 'CHECK: ' + str((cash, bonus))}")
    # print(f"  test customer: {cust.name}")

    # frappe.db.commit()
    # return {"customer": cust.name, "cash": cash, "bonus": bonus, "pass": ok}
    return "OK"