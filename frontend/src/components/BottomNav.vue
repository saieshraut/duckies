<script setup>
import { RouterLink } from "vue-router";

const tabs = [
  { to: "/", label: "Home", icon: "M3 12l9-9 9 9M5 10v10h14V10" },
  { to: "/events", label: "Events", icon: "M8 7V3m8 4V3M4 11h16M5 5h14a1 1 0 011 1v13a1 1 0 01-1 1H5a1 1 0 01-1-1V6a1 1 0 011-1z" },
  { to: "/menu", label: "Menu", icon: "M4 6h16M4 12h16M4 18h10" },
  { to: "/wallet", label: "Wallet", icon: "M3 7h18v10a2 2 0 01-2 2H5a2 2 0 01-2-2V7zm0 0l2-3h14l2 3M16 13h.01" },
];
</script>

<template>
  <nav class="grid grid-cols-4 border-t border-gray-100 bg-white/95 pb-[env(safe-area-inset-bottom)] backdrop-blur">
    <RouterLink
      v-for="t in tabs"
      :key="t.to"
      :to="t.to"
      class="flex flex-col items-center gap-0.5 py-2 text-[11px] font-medium text-gray-400 transition-colors"
      active-class="!text-duck-600"
    >
      <svg class="h-6 w-6" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" :d="t.icon" />
      </svg>
      {{ t.label }}
    </RouterLink>
  </nav>
</template>
