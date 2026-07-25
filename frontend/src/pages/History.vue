<script setup>
import { ref, onMounted } from "vue";
import { api } from "@/lib/api";
import { inr, dateLabel } from "@/lib/format";
import PageHeader from "@/components/PageHeader.vue";
import Spinner from "@/components/Spinner.vue";
import EmptyState from "@/components/EmptyState.vue";

const loading = ref(true);
const loadingMore = ref(false);
const txns = ref([]);
const start = ref(0);
const done = ref(false);
const PAGE = 20;

onMounted(load);

async function load() {
  loading.value = true;
  try {
    const r = await api.transactions(PAGE, 0);
    txns.value = r.transactions || [];
    start.value = txns.value.length;
    done.value = txns.value.length < PAGE;
  } finally {
    loading.value = false;
  }
}

async function more() {
  if (done.value || loadingMore.value) return;
  loadingMore.value = true;
  try {
    const r = await api.transactions(PAGE, start.value);
    const rows = r.transactions || [];
    txns.value.push(...rows);
    start.value += rows.length;
    if (rows.length < PAGE) done.value = true;
  } finally {
    loadingMore.value = false;
  }
}

const isCredit = (t) => t.direction === "Credit";
</script>

<template>
  <div class="pb-6">
    <PageHeader title="Transaction history" />
    <Spinner v-if="loading" />
    <EmptyState v-else-if="!txns.length" title="No transactions yet" />
    <template v-else>
      <ul class="divide-y divide-gray-100">
        <li v-for="t in txns" :key="t.name" class="flex items-center justify-between px-4 py-3">
          <div class="min-w-0">
            <p class="font-medium text-gray-900">{{ t.transaction_type }}</p>
            <p class="text-[11px] text-gray-400">
              {{ dateLabel(t.posting_datetime) }} · {{ t.bucket }} bucket
              <span v-if="t.remarks"> · {{ t.remarks }}</span>
            </p>
          </div>
          <div class="shrink-0 text-right">
            <p :class="['font-bold', isCredit(t) ? 'text-emerald-600' : 'text-gray-800']">
              {{ isCredit(t) ? "+" : "−" }}{{ inr(t.amount) }}
            </p>
            <p class="text-[11px] text-gray-400">bal {{ inr(t.balance_after) }}</p>
          </div>
        </li>
      </ul>
      <div class="px-4 py-4">
        <button v-if="!done" @click="more" :disabled="loadingMore"
          class="w-full rounded-xl bg-gray-50 py-2.5 text-sm font-semibold text-gray-600">
          {{ loadingMore ? "Loading…" : "Load more" }}
        </button>
        <p v-else class="text-center text-xs text-gray-400">That's everything</p>
      </div>
    </template>
  </div>
</template>
