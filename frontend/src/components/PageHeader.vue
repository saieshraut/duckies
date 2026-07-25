<script setup>
import { useRouter } from "vue-router";
defineProps({ title: String, back: Boolean });
const router = useRouter();
</script>
<template>
  <header class="sticky top-0 z-10 flex items-center gap-3 border-b border-gray-100 bg-white/95 px-4 py-3 backdrop-blur">
    <button v-if="back" @click="router.back()" class="-ml-1 rounded-lg p-1 text-gray-500 hover:bg-gray-100">
      <svg class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7" />
      </svg>
    </button>
    <h1 class="text-lg font-bold text-gray-900">{{ title }}</h1>
    <slot name="actions" />
  </header>
</template>
