<script setup>
defineProps({ title: String, subtitle: String });
</script>
<template>
  <div class="flex flex-col items-center px-6 py-16 text-center">
    <div class="mb-3 flex h-14 w-14 items-center justify-center rounded-full bg-duck-50 text-2xl">🦆</div>
    <p class="font-semibold text-gray-800">{{ title }}</p>
    <p v-if="subtitle" class="mt-1 text-sm text-gray-500">{{ subtitle }}</p>
    <slot />
  </div>
</template>
