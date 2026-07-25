<script setup>
defineProps({
  loading: Boolean, disabled: Boolean,
  variant: { type: String, default: "primary" },
});
const styles = {
  primary: "bg-duck-500 text-white hover:bg-duck-600 active:bg-duck-700",
  ghost: "bg-duck-50 text-duck-700 hover:bg-duck-100",
  outline: "border border-gray-200 text-gray-700 hover:bg-gray-50",
  danger: "bg-red-50 text-red-600 hover:bg-red-100",
};
</script>
<template>
  <button
    :disabled="disabled || loading"
    :class="[styles[variant], 'flex w-full items-center justify-center gap-2 rounded-xl px-4 py-3 text-sm font-semibold transition-colors disabled:opacity-50']"
  >
    <span v-if="loading" class="h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white" />
    <slot />
  </button>
</template>
