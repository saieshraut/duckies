<script setup>
import { ref, computed, onMounted } from "vue";
import { api } from "@/lib/api";
import { inr } from "@/lib/format";
import PageHeader from "@/components/PageHeader.vue";
import Spinner from "@/components/Spinner.vue";
import EmptyState from "@/components/EmptyState.vue";

const loading = ref(true);
const sections = ref([]);
const activeSection = ref(0);
const activeCategory = ref(null); // null = "All"

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
</script>

<template>
  <div class="pb-6">
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

      <!-- Items (view only) -->
      <EmptyState v-if="!visibleItems.length" title="Nothing here yet" />
      <ul v-else class="divide-y divide-gray-50">
        <li v-for="it in visibleItems" :key="it.item_code" class="flex items-center gap-3 px-4 py-3">
          <div class="flex h-16 w-16 shrink-0 items-center justify-center overflow-hidden rounded-xl bg-duck-50 text-2xl">
            <img v-if="it.image" :src="it.image" :alt="it.item_name" class="h-full w-full object-cover" />
            <span v-else>{{ activeSection === 1 ? "🍸" : "🍽️" }}</span>
          </div>
          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-1.5">
              <p class="truncate font-semibold text-gray-900">{{ it.item_name }}</p>
              <span v-if="it.category" class="shrink-0 rounded bg-gray-100 px-1.5 py-0.5 text-[10px] font-medium text-gray-500">{{ it.category }}</span>
            </div>
            <p v-if="it.description" class="mt-0.5 line-clamp-2 text-xs text-gray-400">{{ it.description }}</p>
          </div>
          <span class="shrink-0 text-sm font-bold text-duck-600">{{ inr(it.standard_rate) }}</span>
        </li>
      </ul>

      <p class="px-4 py-6 text-center text-xs text-gray-400">
        Order at the counter or your table — pay with your Duckie's wallet.
      </p>
    </template>
  </div>
</template>
