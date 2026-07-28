<script setup>
import { ref, computed, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { session } from "@/stores/session";
import { api } from "@/lib/api";
import { inr, dateLabel, timeLabel } from "@/lib/format";
import { toast } from "@/lib/toast";
import PageHeader from "@/components/PageHeader.vue";
import Spinner from "@/components/Spinner.vue";
import UiButton from "@/components/UiButton.vue";

const route = useRoute();
const router = useRouter();
const loading = ref(true);
const booking = ref(false);
const event = ref(null);
const seats = ref(1);

onMounted(async () => {
  try {
    // events() returns a list; find this one by name
    const list = await api.events({ limit: 200 });
    event.value = (list || []).find((e) => e.name === route.params.name) || null;
  } finally {
    loading.value = false;
  }
});

const total = computed(() => (event.value?.price || 0) * seats.value);
const maxSeats = computed(() => Math.min(event.value?.seats_left || 0, 8));

const cancellationText = computed(() => {
  const e = event.value;
  if (!e) return "";
  if (!e.is_cancellable) return "This event cannot be cancelled once booked.";

  const hrs = Number(e.cancellation_cutoff_hours || 0);
  const window = hrs === 1 ? "1 hour" : `${hrs} hours`;

  if (e.refund_type === "Flat") {
    const amt = Number(e.refund_flat_amount || 0);
    return amt > 0
      ? `Cancel up to ${window} before start for a refund of ${inr(amt)} per seat.`
      : `Cancel up to ${window} before start — no refund is given.`;
  }
  const pct = e.refund_percentage == null ? 100 : Number(e.refund_percentage);
  if (pct <= 0) return `Cancel up to ${window} before start — no refund is given.`;
  if (pct >= 100) return `Free cancellation up to ${window} before the event starts.`;
  return `Cancel up to ${window} before start for a ${pct}% refund.`;
});

async function book() {
  if (!session.isLoggedIn) {
    router.push({ name: "login", query: { redirect: route.fullPath } });
    return;
  }
  if ((session.user?.wallet_balance ?? 0) < total.value) {
    toast("Insufficient balance. Please recharge.", "error");
    router.push("/recharge");
    return;
  }
  const seatLabel = seats.value === 1 ? "1 seat" : `${seats.value} seats`;
  if (!confirm(`Book ${seatLabel} for ${event.value.event_name}? ${inr(total.value)} will be deducted from your wallet.`)) {
    return;
  }
  booking.value = true;
  try {
    const r = await api.bookEvent(event.value.name, seats.value);
    await session.refreshBalance();
    toast(r.message || "Booking confirmed!", "success");
    router.replace("/bookings");
  } catch (e) {
    toast(e.message || "Booking failed", "error");
  } finally {
    booking.value = false;
  }
}
</script>

<template>
  <div class="pb-28">
    <PageHeader :title="event?.event_name || 'Event'" back />
    <Spinner v-if="loading" />
    <template v-else-if="event">
      <div class="flex h-40 items-center justify-center bg-duck-100 text-5xl">🎟️</div>
      <div class="px-5 py-4">
        <h1 class="text-xl font-extrabold text-gray-900">{{ event.event_name }}</h1>
        <p class="mt-1 text-sm text-gray-500">{{ event.space }}</p>

        <div class="mt-4 grid grid-cols-2 gap-3">
          <div class="rounded-xl bg-gray-50 px-3 py-2.5">
            <p class="text-[11px] text-gray-400">When</p>
            <p class="text-sm font-semibold text-gray-800">{{ dateLabel(event.date) }}</p>
            <p class="text-xs text-gray-500">{{ timeLabel(event.start_time) }}</p>
          </div>
          <div class="rounded-xl bg-gray-50 px-3 py-2.5">
            <p class="text-[11px] text-gray-400">Availability</p>
            <p class="text-sm font-semibold" :class="event.seats_left > 0 ? 'text-emerald-600' : 'text-red-500'">
              {{ event.seats_left }} / {{ event.capacity }} left
            </p>
          </div>
        </div>

        <div
          class="mt-3 flex items-start gap-2 rounded-xl px-3 py-2.5 text-xs"
          :class="event.is_cancellable ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-600'"
        >
          <span class="mt-0.5">{{ event.is_cancellable ? "✓" : "✕" }}</span>
          <span>{{ cancellationText }}</span>
        </div>

        <div v-if="event.description" class="mt-4 text-sm leading-relaxed text-gray-600" v-html="event.description" />

        <!-- Seat selector -->
        <div v-if="event.seats_left > 0" class="mt-5">
          <p class="mb-2 text-sm font-semibold text-gray-700">Seats</p>
          <div class="flex items-center gap-4">
            <button @click="seats = Math.max(1, seats - 1)" class="flex h-10 w-10 items-center justify-center rounded-full bg-gray-100 text-xl font-bold text-gray-600">−</button>
            <span class="w-8 text-center text-lg font-extrabold">{{ seats }}</span>
            <button @click="seats = Math.min(maxSeats, seats + 1)" class="flex h-10 w-10 items-center justify-center rounded-full bg-gray-100 text-xl font-bold text-gray-600">+</button>
          </div>
        </div>
      </div>

      <!-- Sticky book bar -->
      <div class="fixed inset-x-0 bottom-0 z-20 mx-auto max-w-md border-t border-gray-100 bg-white px-5 py-3 pb-[calc(0.75rem+env(safe-area-inset-bottom))]">
        <div class="mb-2 flex items-center justify-between">
          <span class="text-sm text-gray-500">Total</span>
          <span class="text-lg font-extrabold text-gray-900">{{ inr(total) }}</span>
        </div>
        <UiButton :loading="booking" :disabled="event.seats_left < 1" @click="book">
          {{ event.seats_left < 1 ? "Sold out" : "Book with wallet" }}
        </UiButton>
      </div>
    </template>
    <EmptyState v-else title="Event not found" />
  </div>
</template>
