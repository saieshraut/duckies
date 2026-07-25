<script setup>
import { ref, onMounted } from "vue";
import { RouterLink } from "vue-router";
import { session } from "@/stores/session";
import { api } from "@/lib/api";
import { inr, inr2, dateLabel } from "@/lib/format";
import Spinner from "@/components/Spinner.vue";

const loading = ref(true);
const txns = ref([]);

onMounted(async () => {
  try {
    await session.refreshBalance();
    const r = await api.transactions(5, 0);
    txns.value = r.transactions || [];
  } finally {
    loading.value = false;
  }
});

const u = session.user;
</script>

<template>
  <div class="pb-6">
    <!-- Balance card -->
    <div class="bg-gradient-to-br from-duck-500 to-duck-700 px-5 pb-8 pt-6 text-white">
      <div class="flex items-center justify-between">
        <div>
          <p class="text-sm text-duck-100">Hi {{ u?.name?.split(" ")[0] }} 👋</p>
          <p class="text-xs text-duck-200">Wallet balance</p>
        </div>
        <button @click="session.logout()" class="rounded-lg bg-white/15 p-2 text-white/90 hover:bg-white/25">
          <svg class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" d="M17 16l4-4m0 0l-4-4m4 4H7M13 16v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
          </svg>
        </button>
      </div>

      <p class="mt-3 text-4xl font-extrabold tracking-tight">{{ inr2(u?.wallet_balance) }}</p>

      <div class="mt-4 flex gap-3">
        <div class="flex-1 rounded-xl bg-white/15 px-3 py-2 backdrop-blur">
          <p class="text-[11px] text-duck-100">Cash (refundable)</p>
          <p class="text-lg font-bold">{{ inr(u?.cash_balance) }}</p>
        </div>
        <div class="flex-1 rounded-xl bg-white/15 px-3 py-2 backdrop-blur">
          <p class="text-[11px] text-duck-100">Bonus</p>
          <p class="text-lg font-bold">{{ inr(u?.bonus_balance) }}</p>
        </div>
      </div>

      <p v-if="u?.wallet_expiry" class="mt-3 text-[11px] text-duck-200">
        Balance valid until {{ dateLabel(u.wallet_expiry) }}
      </p>
    </div>

    <!-- Quick actions -->
    <div class="-mt-4 px-4">
      <div class="grid grid-cols-2 gap-3">
        <RouterLink to="/recharge" class="flex flex-col items-center gap-1 rounded-2xl bg-white px-4 py-4 shadow-md ring-1 ring-gray-100">
          <span class="flex h-10 w-10 items-center justify-center rounded-full bg-duck-100 text-duck-600">
            <svg class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" /></svg>
          </span>
          <span class="text-sm font-semibold text-gray-800">Add money</span>
        </RouterLink>
        <RouterLink to="/history" class="flex flex-col items-center gap-1 rounded-2xl bg-white px-4 py-4 shadow-md ring-1 ring-gray-100">
          <span class="flex h-10 w-10 items-center justify-center rounded-full bg-duck-100 text-duck-600">
            <svg class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
          </span>
          <span class="text-sm font-semibold text-gray-800">History</span>
        </RouterLink>
      </div>
    </div>

    <!-- Recent activity -->
    <div class="mt-6 px-4">
      <div class="mb-2 flex items-center justify-between">
        <h2 class="text-sm font-bold text-gray-800">Recent activity</h2>
        <RouterLink to="/history" class="text-xs font-semibold text-duck-600">See all</RouterLink>
      </div>
      <Spinner v-if="loading" />
      <div v-else-if="!txns.length" class="rounded-xl bg-gray-50 px-4 py-6 text-center text-sm text-gray-400">
        No transactions yet
      </div>
      <ul v-else class="space-y-1.5">
        <li v-for="t in txns" :key="t.name" class="flex items-center justify-between rounded-xl bg-white px-3 py-2.5 ring-1 ring-gray-100">
          <div>
            <p class="text-sm font-medium text-gray-800">{{ t.transaction_type }}</p>
            <p class="text-[11px] text-gray-400">{{ dateLabel(t.posting_datetime) }} · {{ t.bucket }}</p>
          </div>
          <span :class="['text-sm font-bold', t.direction === 'Credit' ? 'text-emerald-600' : 'text-gray-700']">
            {{ t.direction === "Credit" ? "+" : "−" }}{{ inr(t.amount) }}
          </span>
        </li>
      </ul>
    </div>
  </div>
</template>
