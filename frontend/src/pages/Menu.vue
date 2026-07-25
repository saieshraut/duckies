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
const sections = ref([]);
const activeSection = ref(0);
const activeCategory = ref(null); // null = "All"
const cart = ref({});

onMounted(async () => {
  try {
    const r = await api.menu();
    sections.value = r.sections || [];
  } finally {
    loading.value = false;
  }
});

const section = computed(() => sections.value[activeSection.value] || null);

const visibleItems = computed(() => {
  if (!section.value) return [];
  if (!activeCategory.value) return section.value.items;
  return section.value.items.filter((it) => it.category === activeCategory.value);
});

function pickSection(i) {
  activeSection.value = i;
  activeCategory.value = null;
}

const cartItems = computed(() => Object.values(cart.value));
const cartCount = computed(() => cartItems.value.reduce((n, c) => n + c.qty, 0));
const cartTotal = computed(() =>
  cartItems.value.reduce((s, c) => s + (c.item.standard_rate || 0) * c.qty, 0));

function add(item) {
  if (item.age_restricted) {
    toast("Alcohol is ordered at the bar (18+, in person).", "info");
    return;
  }
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
    <EmptyState v-else-if="!sections.length" title="Menu coming soon" subtitle="Our kitchen is getting set up." />

    <template v-else>
      <!-- Section tabs -->
      <div class="flex border-b border-gray-100">
        <button
          v-for="(s, i) in sections"
          :key="s.name"
          @click="pickSection(i)"
          :class="[
            'flex-1 border-b-2 px-4 py-3 text-sm font-bold transition-colors',
            activeSection === i ? 'border-duck-500 text-duck-600' : 'border-transparent text-gray-400',
          ]"
        >
          {{ s.name }}
        </button>
      </div>

      <!-- Category filter chips -->
      <div v-if="section && section.categories.length" class="flex gap-2 overflow-x-auto px-4 py-3">
        <button
          @click="activeCategory = null"
          :class="['shrink-0 rounded-full px-3 py-1.5 text-xs font-semibold', !activeCategory ? 'bg-duck-500 text-white' : 'bg-gray-100 text-gray-600']"
        >All</button>
        <button
          v-for="c in section.categories"
          :key="c"
          @click="activeCategory = c"
          :class="['shrink-0 rounded-full px-3 py-1.5 text-xs font-semibold', activeCategory === c ? 'bg-duck-500 text-white' : 'bg-gray-100 text-gray-600']"
        >{{ c }}</button>
      </div>

      <!-- Items -->
      <EmptyState v-if="!visibleItems.length" title="Nothing here yet" />
      <ul v-else>
        <li v-for="it in visibleItems" :key="it.item_code" class="flex items-center gap-3 px-4 py-3">
          <div class="flex h-14 w-14 shrink-0 items-center justify-center overflow-hidden rounded-xl bg-duck-50 text-xl">
            <img v-if="it.image" :src="it.image" class="h-full w-full object-cover" />
            <span v-else>{{ activeSection === 1 ? "🍸" : "🍽️" }}</span>
          </div>
          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-1.5">
              <p class="truncate font-semibold text-gray-900">{{ it.item_name }}</p>
              <span v-if="it.category" class="shrink-0 rounded bg-gray-100 px-1.5 py-0.5 text-[10px] font-medium text-gray-500">{{ it.category }}</span>
            </div>
            <p v-if="it.description" class="truncate text-[11px] text-gray-400">{{ it.description }}</p>
            <p class="mt-0.5 text-sm font-bold text-duck-600">{{ inr(it.standard_rate) }}</p>
          </div>

          <div v-if="it.age_restricted" class="shrink-0 text-right">
            <span class="rounded-lg bg-amber-50 px-2 py-1 text-[10px] font-semibold text-amber-700">18+ at bar</span>
          </div>
          <div v-else-if="cart[it.item_code]" class="flex shrink-0 items-center gap-2">
            <button @click="remove(it)" class="flex h-8 w-8 items-center justify-center rounded-full bg-gray-100 font-bold text-gray-600">−</button>
            <span class="w-5 text-center text-sm font-bold">{{ cart[it.item_code].qty }}</span>
            <button @click="add(it)" class="flex h-8 w-8 items-center justify-center rounded-full bg-duck-500 font-bold text-white">+</button>
          </div>
          <button v-else @click="add(it)" class="shrink-0 rounded-lg bg-duck-50 px-3 py-1.5 text-xs font-bold text-duck-700">Add</button>
        </li>
      </ul>
    </template>

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
