<script setup>
import { ref, onMounted } from "vue";
import { session } from "@/stores/session";
import { api } from "@/lib/api";
import { inr, dateLabel, timeLabel } from "@/lib/format";
import { toast } from "@/lib/toast";
import PageHeader from "@/components/PageHeader.vue";
import Spinner from "@/components/Spinner.vue";
import EmptyState from "@/components/EmptyState.vue";

const loading = ref(true);
const bookings = ref([]);
const cancelling = ref(null);

onMounted(load);

async function load() {
  loading.value = true;
  try {
    bookings.value = await api.myBookings(50, 0);
  } finally {
    loading.value = false;
  }
}

async function cancel(b) {
  if (!confirm("Cancel this booking? Your wallet will be refunded.")) return;
  cancelling.value = b.name;
  try {
    const r = await api.cancelBooking(b.name);
    await session.refreshBalance();
    toast(r.message || "Booking cancelled", "success");
    await load();
  } catch (e) {
    toast(e.message || "Could not cancel", "error");
  } finally {
    cancelling.value = null;
  }
}

const badge = (s) => ({
  Confirmed: "bg-emerald-50 text-emerald-700",
  Cancelled: "bg-gray-100 text-gray-500",
  Attended: "bg-blue-50 text-blue-700",
}[s] || "bg-gray-100 text-gray-500");
</script>

<template>
  <div>
    <PageHeader title="My bookings" />
    <Spinner v-if="loading" />
    <EmptyState v-else-if="!bookings.length" title="No bookings yet" subtitle="Browse events and book your spot." />
    <ul v-else class="divide-y divide-gray-100">
      <li v-for="b in bookings" :key="b.name" class="px-4 py-3">
        <div class="flex items-start justify-between">
          <div class="min-w-0">
            <p class="truncate font-semibold text-gray-900">{{ b.event_name }}</p>
            <p class="text-xs text-gray-500">{{ b.space }} · {{ dateLabel(b.date) }} · {{ timeLabel(b.start_time) }}</p>
            <p class="mt-1 text-xs text-gray-500">{{ b.seats }} seat(s) · {{ inr(b.amount_paid) }}</p>
          </div>
          <span :class="['shrink-0 rounded-full px-2.5 py-1 text-[11px] font-semibold', badge(b.status)]">{{ b.status }}</span>
        </div>
        <button v-if="b.status === 'Confirmed'" @click="cancel(b)" :disabled="cancelling === b.name"
          class="mt-2 text-xs font-semibold text-red-500 disabled:opacity-50">
          {{ cancelling === b.name ? "Cancelling…" : "Cancel booking" }}
        </button>
      </li>
    </ul>
  </div>
</template>
