<script setup>
import { ref, computed, onMounted } from "vue";
import { useRouter } from "vue-router";
import { session } from "@/stores/session";
import { api } from "@/lib/api";
import { inr } from "@/lib/format";
import { toast } from "@/lib/toast";
import PageHeader from "@/components/PageHeader.vue";
import UiButton from "@/components/UiButton.vue";

const router = useRouter();
const presets = [500, 1000, 2000, 5000];
const amount = ref(2000);
const offers = ref([]);
const loading = ref(false);
const polling = ref(false);

onMounted(async () => {
  try {
    offers.value = await api.activeOffers();
  } catch { /* offers optional */ }
  await loadRazorpay();
});

// Best matching offer for the current amount (mirrors backend logic)
const matchedBonus = computed(() => {
  let best = 0;
  for (const o of offers.value) {
    if (amount.value < o.min_recharge_amount) continue;
    const b = o.bonus_type === "Fixed Amount"
      ? o.bonus_amount
      : (amount.value * o.bonus_percent) / 100;
    if (b > best) best = b;
  }
  return best;
});

function loadRazorpay() {
  return new Promise((resolve) => {
    if (window.Razorpay) return resolve();
    const s = document.createElement("script");
    s.src = "https://checkout.razorpay.com/v1/checkout.js";
    s.onload = resolve;
    s.onerror = resolve;
    document.head.appendChild(s);
  });
}

async function recharge() {
  if (amount.value < 100) {
    toast("Minimum recharge is ₹100", "error");
    return;
  }
  loading.value = true;
  try {
    const order = await api.createRechargeOrder(amount.value);
    if (!window.Razorpay) {
      toast("Payment unavailable. Please try again.", "error");
      return;
    }
    const rzp = new window.Razorpay({
      key: order.key_id,
      order_id: order.order_id,
      amount: order.amount,
      currency: order.currency,
      name: order.name,
      description: order.description,
      prefill: { email: session.user?.email, contact: session.user?.mobile },
      theme: { color: "#fe7f11" },
      handler: () => pollForCredit(),
      modal: { ondismiss: () => { loading.value = false; } },
    });
    rzp.on("payment.failed", () => {
      toast("Payment failed. Please try again.", "error");
      loading.value = false;
    });
    rzp.open();
  } catch (e) {
    toast(e.message || "Could not start payment", "error");
    loading.value = false;
  }
}

// Wallet is credited by the verified webhook — poll balance until it lands.
async function pollForCredit() {
  polling.value = true;
  const before = session.user?.wallet_balance ?? 0;
  for (let i = 0; i < 12; i++) {
    await new Promise((r) => setTimeout(r, 1500));
    await session.refreshBalance();
    if ((session.user?.wallet_balance ?? 0) > before) {
      toast("Wallet recharged!", "success");
      polling.value = false;
      loading.value = false;
      router.replace("/wallet");
      return;
    }
  }
  polling.value = false;
  loading.value = false;
  toast("Payment received — balance will update shortly.", "info");
  router.replace("/wallet");
}
</script>

<template>
  <div>
    <PageHeader title="Add money" back />
    <div class="px-5 py-5">
      <p class="text-sm text-gray-500">Enter amount</p>
      <div class="mt-2 flex items-center rounded-2xl border border-gray-200 px-4 py-3 focus-within:border-duck-400 focus-within:ring-2 focus-within:ring-duck-100">
        <span class="text-2xl font-bold text-gray-400">₹</span>
        <input v-model.number="amount" type="number" min="100" inputmode="numeric"
          class="w-full bg-transparent pl-2 text-2xl font-extrabold text-gray-900 outline-none" />
      </div>

      <div class="mt-3 grid grid-cols-4 gap-2">
        <button v-for="p in presets" :key="p" @click="amount = p"
          :class="['rounded-xl py-2 text-sm font-semibold transition-colors', amount === p ? 'bg-duck-500 text-white' : 'bg-duck-50 text-duck-700']">
          ₹{{ p }}
        </button>
      </div>

      <div v-if="matchedBonus > 0" class="mt-4 flex items-center gap-2 rounded-xl bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
        <span class="text-lg">🎁</span>
        <span>You'll get <b>{{ inr(matchedBonus) }} bonus</b> — total {{ inr(amount + matchedBonus) }} in your wallet!</span>
      </div>

      <div v-if="offers.length" class="mt-5">
        <p class="mb-2 text-xs font-bold uppercase tracking-wide text-gray-400">Offers</p>
        <ul class="space-y-2">
          <li v-for="o in offers" :key="o.offer_name" class="rounded-xl border border-dashed border-duck-200 bg-duck-50/50 px-4 py-2.5 text-sm">
            <p class="font-semibold text-gray-800">{{ o.offer_name }}</p>
            <p class="text-xs text-gray-500">
              Load {{ inr(o.min_recharge_amount) }}+ and get
              {{ o.bonus_type === "Fixed Amount" ? inr(o.bonus_amount) : o.bonus_percent + "%" }} bonus
            </p>
          </li>
        </ul>
      </div>

      <div class="mt-6">
        <UiButton :loading="loading || polling" @click="recharge">
          {{ polling ? "Confirming payment…" : `Pay ${inr(amount)}` }}
        </UiButton>
        <p class="mt-3 text-center text-[11px] text-gray-400">
          Secure payment via Razorpay. Balance is usable only at Duckie's.
        </p>
      </div>
    </div>
  </div>
</template>
