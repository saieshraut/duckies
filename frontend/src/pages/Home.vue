<script setup>
import { ref, onMounted } from "vue";
import { RouterLink } from "vue-router";
import { session } from "@/stores/session";
import { api } from "@/lib/api";
import { inr, dateLabel, timeLabel } from "@/lib/format";
import Spinner from "@/components/Spinner.vue";

const loading = ref(true);
const spaces = ref([]);
const featured = ref([]);
const upcoming = ref([]);

onMounted(async () => {
  try {
    const [sp, feat, ev] = await Promise.all([
      api.spaces(),
      api.events({ featured: 1, limit: 6 }),
      api.events({ limit: 5 }),
    ]);
    spaces.value = sp || [];
    featured.value = feat || [];
    // Upcoming excludes anything already shown as featured, to avoid repeats.
    const featIds = new Set((feat || []).map((e) => e.name));
    upcoming.value = (ev || []).filter((e) => !featIds.has(e.name));
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
      <!-- Featured events -->
      <section v-if="featured.length" class="mt-5">
        <div class="mb-2 flex items-center justify-between px-4">
          <h2 class="text-sm font-bold text-gray-800">✨ Featured</h2>
          <RouterLink to="/events" class="text-xs font-semibold text-duck-600">All events</RouterLink>
        </div>
        <div class="-mx-0 flex snap-x snap-mandatory gap-3 overflow-x-auto px-4 pb-2">
          <RouterLink
            v-for="e in featured"
            :key="e.name"
            :to="`/events/${e.name}`"
            class="w-72 shrink-0 snap-start overflow-hidden rounded-2xl bg-white shadow-md ring-1 ring-gray-100"
          >
            <div class="relative h-40 w-full bg-duck-100">
              <img v-if="e.image" :src="e.image" :alt="e.event_name" class="h-full w-full object-cover" />
              <div v-else class="flex h-full w-full items-center justify-center text-5xl">🎟️</div>
              <div class="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent" />
              <span class="absolute left-3 top-3 rounded-full bg-duck-500 px-2 py-0.5 text-[10px] font-bold text-white">FEATURED</span>
              <div class="absolute bottom-0 left-0 right-0 p-3">
                <p class="truncate text-base font-extrabold text-white drop-shadow">{{ e.event_name }}</p>
                <p class="text-xs text-white/90 drop-shadow">{{ dateLabel(e.date) }} · {{ timeLabel(e.start_time) }}</p>
              </div>
            </div>
            <div class="flex items-center justify-between px-3 py-2.5">
              <span class="text-xs text-gray-500">{{ e.space }}</span>
              <span class="text-sm font-bold text-duck-600">{{ inr(e.price) }}</span>
            </div>
          </RouterLink>
        </div>
      </section>

      <!-- Upcoming events -->
      <section v-if="upcoming.length" class="mt-5 px-4">
        <div class="mb-2 flex items-center justify-between">
          <h2 class="text-sm font-bold text-gray-800">Happening soon</h2>
          <RouterLink to="/events" class="text-xs font-semibold text-duck-600">All events</RouterLink>
        </div>
        <div class="-mx-4 flex gap-3 overflow-x-auto px-4 pb-2">
          <RouterLink v-for="e in upcoming" :key="e.name" :to="`/events/${e.name}`"
            class="w-44 shrink-0 overflow-hidden rounded-2xl bg-white shadow ring-1 ring-gray-100">
            <div class="h-24 overflow-hidden bg-duck-100">
              <img v-if="e.image" :src="e.image" :alt="e.event_name" class="h-full w-full object-cover" />
              <div v-else class="flex h-full items-center justify-center text-3xl">🎟️</div>
            </div>
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
          <RouterLink
            v-for="s in spaces"
            :key="s.name"
            :to="s.is_bookable ? { name: 'events', query: { space: s.name } } : ''"
            :class="[
              'block overflow-hidden rounded-2xl bg-white shadow-sm ring-1 ring-gray-100',
              s.is_bookable ? 'active:opacity-90' : 'cursor-default',
            ]"
          >
            <!-- Image banner -->
            <div class="relative h-36 w-full bg-duck-100">
              <img
                v-if="s.image"
                :src="s.image"
                :alt="s.space_name"
                class="h-full w-full object-cover"
              />
              <div v-else class="flex h-full w-full items-center justify-center text-4xl">🏓</div>
              <!-- gradient + title overlay -->
              <div class="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent" />
              <div class="absolute bottom-0 left-0 right-0 p-3">
                <p class="text-base font-extrabold text-white drop-shadow">{{ s.space_name }}</p>
                <p v-if="s.tagline" class="truncate text-xs text-white/90 drop-shadow">{{ s.tagline }}</p>
              </div>
            </div>
            <!-- Footer row: hint to view events -->
            <div v-if="s.is_bookable" class="flex items-center justify-between px-4 py-2.5">
              <span class="text-xs font-medium text-gray-500">View events here</span>
              <svg class="h-4 w-4 text-duck-500" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7" />
              </svg>
            </div>
          </RouterLink>
        </div>
      </section>
    </template>
  </div>
</template>
