<script setup>
import { ref, onMounted } from "vue";
import { RouterLink } from "vue-router";
import { session } from "@/stores/session";
import { api } from "@/lib/api";
import { inr, dateLabel, timeLabel } from "@/lib/format";
import Spinner from "@/components/Spinner.vue";

const loading = ref(true);
const spaces = ref([]);
const upcoming = ref([]);

onMounted(async () => {
  try {
    const [sp, ev] = await Promise.all([api.spaces(), api.events({ limit: 5 })]);
    spaces.value = sp || [];
    upcoming.value = ev || [];
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <div class="pb-6">
    <!-- Hero -->
    <div class="bg-gradient-to-br from-duck-500 to-duck-700 px-5 pb-6 pt-8 text-white">
      <div class="flex items-center gap-2">
        <span class="text-3xl">🦆</span>
        <h1 class="text-2xl font-extrabold">Duckie's</h1>
      </div>
      <p class="mt-1 text-sm text-duck-100">Play. Sip. Groove. All on your wallet.</p>

      <RouterLink v-if="!session.isLoggedIn" to="/login"
        class="mt-4 inline-flex rounded-xl bg-white px-5 py-2.5 text-sm font-bold text-duck-700 shadow">
        Sign in / Join
      </RouterLink>
      <RouterLink v-else to="/wallet"
        class="mt-4 inline-flex items-center gap-2 rounded-xl bg-white/15 px-4 py-2 text-sm font-semibold backdrop-blur">
        Wallet balance: {{ inr(session.user?.wallet_balance) }}
      </RouterLink>
    </div>

    <Spinner v-if="loading" />
    <template v-else>
      <!-- Upcoming events -->
      <section v-if="upcoming.length" class="mt-5 px-4">
        <div class="mb-2 flex items-center justify-between">
          <h2 class="text-sm font-bold text-gray-800">Happening soon</h2>
          <RouterLink to="/events" class="text-xs font-semibold text-duck-600">All events</RouterLink>
        </div>
        <div class="-mx-4 flex gap-3 overflow-x-auto px-4 pb-2">
          <RouterLink v-for="e in upcoming" :key="e.name" :to="`/events/${e.name}`"
            class="w-44 shrink-0 overflow-hidden rounded-2xl bg-white shadow ring-1 ring-gray-100">
            <div class="flex h-24 items-center justify-center bg-duck-100 text-3xl">🎟️</div>
            <div class="p-3">
              <p class="truncate text-sm font-bold text-gray-800">{{ e.event_name }}</p>
              <p class="mt-0.5 text-[11px] text-gray-500">{{ dateLabel(e.date) }} · {{ timeLabel(e.start_time) }}</p>
              <p class="mt-1 text-sm font-bold text-duck-600">{{ inr(e.price) }}</p>
            </div>
          </RouterLink>
        </div>
      </section>

      <!-- Spaces -->
      <section class="mt-5 px-4">
        <h2 class="mb-2 text-sm font-bold text-gray-800">Our spaces</h2>
        <div class="space-y-3">
          <div v-for="s in spaces" :key="s.name" class="overflow-hidden rounded-2xl bg-white shadow-sm ring-1 ring-gray-100">
            <div class="flex items-center gap-3 p-4">
              <div class="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-duck-100 text-xl">🏓</div>
              <div class="min-w-0">
                <p class="font-bold text-gray-900">{{ s.space_name }}</p>
                <p class="truncate text-xs text-gray-500">{{ s.tagline }}</p>
              </div>
            </div>
          </div>
        </div>
      </section>
    </template>
  </div>
</template>
