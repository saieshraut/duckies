<script setup>
import { ref, computed, onMounted } from "vue";
import { useRouter } from "vue-router";
import { session } from "@/stores/session";
import { api } from "@/lib/api";
import { inr } from "@/lib/format";
import { toast } from "@/lib/toast";
import PageHeader from "@/components/PageHeader.vue";
import Spinner from "@/components/Spinner.vue";
import EmptyState from "@/components/EmptyState.vue";
import UiButton from "@/components/UiButton.vue";

const router = useRouter();
const loading = ref(true);
const placing = ref(false);
const groups = ref({});
const cart = ref({}); // item_code -> {item, qty}

onMounted(async () => {
  try {
    groups.value = await api.menu();
  } finally {
    loading.value = false;
  }
});

const cartItems = computed(() => Object.values(cart.value));
const cartCount = computed(() => cartItems.value.reduce((n, c) => n + c.qty, 0));
const cartTotal = computed(() =>
  cartItems.value.reduce((s, c) => s + (c.item.standard_rate || 0) * c.qty, 0));

function add(item) {
  const c = cart.value[item.item_code];
  if (c) c.qty++;
  else cart.value[item.item_code] = { item, qty: 1 };
}
function remove(item) {
  const c = cart.value[item.item_code];
  if (!c) return;
  c.qty--;
  if (c.qty <= 0) delete cart.value[item.item_code];
}

async function order() {
  if (!session.isLoggedIn) {
    router.push({ name: "login", query: { redirect: "/menu" } });
    return;
  }
  if (session.user.wallet_balance < cartTotal.value) {
    toast("Insufficient balance. Please recharge.", "error");
    router.push("/recharge");
    return;
  }
  placing.value = true;
  try {
    const items = cartItems.value.map((c) => ({ item_code: c.item.item_code, qty: c.qty }));
    const r = await api.placeOrder(items);
    await session.refreshBalance();
    toast(r.message || "Order placed!", "success");
    cart.value = {};
  } catch (e) {
    toast(e.message || "Order failed", "error");
  } finally {
    placing.value = false;
  }
}
</script>

<template>
  <div :class="cartCount ? 'pb-28' : 'pb-6'">
    <PageHeader title="Menu" />
    <Spinner v-if="loading" />
    <EmptyState v-else-if="!Object.keys(groups).length" title="Menu coming soon" subtitle="Our kitchen is getting set up." />

    <div v-else>
      <section v-for="(items, group) in groups" :key="group" class="mt-4">
        <h2 class="px-4 text-xs font-bold uppercase tracking-wide text-gray-400">{{ group }}</h2>
        <ul class="mt-1">
          <li v-for="it in items" :key="it.item_code" class="flex items-center gap-3 px-4 py-3">
            <div class="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-duck-50 text-xl">🍽️</div>
            <div class="min-w-0 flex-1">
              <p class="truncate font-semibold text-gray-900">{{ it.item_name }}</p>
              <p class="text-sm font-bold text-duck-600">{{ inr(it.standard_rate) }}</p>
            </div>
            <div v-if="cart[it.item_code]" class="flex items-center gap-2">
              <button @click="remove(it)" class="flex h-8 w-8 items-center justify-center rounded-full bg-gray-100 font-bold text-gray-600">−</button>
              <span class="w-5 text-center text-sm font-bold">{{ cart[it.item_code].qty }}</span>
              <button @click="add(it)" class="flex h-8 w-8 items-center justify-center rounded-full bg-duck-500 font-bold text-white">+</button>
            </div>
            <button v-else @click="add(it)" class="rounded-lg bg-duck-50 px-3 py-1.5 text-xs font-bold text-duck-700">Add</button>
          </li>
        </ul>
      </section>
    </div>

    <!-- Sticky cart bar -->
    <div v-if="cartCount" class="fixed inset-x-0 bottom-0 z-20 mx-auto max-w-md border-t border-gray-100 bg-white px-5 py-3 pb-[calc(0.75rem+env(safe-area-inset-bottom))]">
      <div class="mb-2 flex items-center justify-between text-sm">
        <span class="text-gray-500">{{ cartCount }} item(s)</span>
        <span class="text-lg font-extrabold text-gray-900">{{ inr(cartTotal) }}</span>
      </div>
      <UiButton :loading="placing" @click="order">Order with wallet</UiButton>
    </div>
  </div>
</template>
