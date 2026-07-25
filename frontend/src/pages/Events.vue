<script setup>
import { ref, onMounted } from "vue";
import { RouterLink } from "vue-router";
import { api } from "@/lib/api";
import { inr, dateLabel, timeLabel } from "@/lib/format";
import PageHeader from "@/components/PageHeader.vue";
import Spinner from "@/components/Spinner.vue";
import EmptyState from "@/components/EmptyState.vue";

const loading = ref(true);
const spaces = ref([]);
const events = ref([]);
const activeSpace = ref(null);

onMounted(async () => {
  const sp = await api.spaces().catch(() => []);
  spaces.value = (sp || []).filter((s) => s.is_bookable);
  await load();
});

async function load() {
  loading.value = true;
  try {
    events.value = await api.events(activeSpace.value ? { space: activeSpace.value } : {});
  } finally {
    loading.value = false;
  }
}

function pick(s) {
  activeSpace.value = activeSpace.value === s ? null : s;
  load();
}
</script>

<template>
  <div>
    <PageHeader title="Events" />

    <!-- Space filter chips -->
    <div class="flex gap-2 overflow-x-auto border-b border-gray-100 px-4 py-3">
      <button @click="pick(null)"
        :class="['shrink-0 rounded-full px-3 py-1.5 text-xs font-semibold', !activeSpace ? 'bg-duck-500 text-white' : 'bg-gray-100 text-gray-600']">
        All
      </button>
      <button v-for="s in spaces" :key="s.name" @click="pick(s.name)"
        :class="['shrink-0 rounded-full px-3 py-1.5 text-xs font-semibold', activeSpace === s.name ? 'bg-duck-500 text-white' : 'bg-gray-100 text-gray-600']">
        {{ s.space_name }}
      </button>
    </div>

    <Spinner v-if="loading" />
    <EmptyState v-else-if="!events.length" title="No upcoming events" subtitle="Check back soon for new sessions." />

    <ul v-else class="divide-y divide-gray-100">
      <RouterLink v-for="e in events" :key="e.name" :to="`/events/${e.name}`" custom v-slot="{ navigate }">
        <li @click="navigate" class="flex cursor-pointer items-center gap-3 px-4 py-3 active:bg-gray-50">
          <div class="flex h-14 w-14 shrink-0 flex-col items-center justify-center rounded-xl bg-duck-100 text-duck-700">
            <span class="text-[10px] font-semibold uppercase">{{ dateLabel(e.date).split(" ")[0] }}</span>
            <span class="text-lg font-extrabold leading-none">{{ dateLabel(e.date).split(" ")[1] }}</span>
          </div>
          <div class="min-w-0 flex-1">
            <p class="truncate font-semibold text-gray-900">{{ e.event_name }}</p>
            <p class="text-xs text-gray-500">{{ e.space }} · {{ timeLabel(e.start_time) }}</p>
            <p class="mt-0.5 text-[11px]" :class="e.seats_left > 0 ? 'text-emerald-600' : 'text-red-500'">
              {{ e.seats_left > 0 ? `${e.seats_left} seats left` : "Sold out" }}
            </p>
          </div>
          <span class="shrink-0 text-sm font-bold text-duck-600">{{ inr(e.price) }}</span>
        </li>
      </RouterLink>
    </ul>
  </div>
</template>
