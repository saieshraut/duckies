<script setup>
import { computed } from "vue";
import { useRoute } from "vue-router";
import { session } from "@/stores/session";
import BottomNav from "@/components/BottomNav.vue";
import { toasts } from "@/lib/toast";

const route = useRoute();
// Hide chrome on auth screens
const bare = computed(() => ["login", "register"].includes(route.name));
</script>

<template>
  <div class="mx-auto flex h-full max-w-md flex-col bg-white shadow-xl">
    <main class="app-scroll flex-1 overflow-y-auto">
      <div v-if="session.loading" class="flex h-full items-center justify-center">
        <div class="h-8 w-8 animate-spin rounded-full border-4 border-duck-200 border-t-duck-500" />
      </div>
      <router-view v-else v-slot="{ Component }">
        <transition name="fade" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </main>
    <BottomNav v-if="!bare" />

    <!-- Toasts -->
    <div class="pointer-events-none fixed inset-x-0 top-3 z-50 mx-auto flex max-w-md flex-col items-center gap-2 px-4">
      <transition-group name="toast">
        <div
          v-for="t in toasts"
          :key="t.id"
          :class="[
            'pointer-events-auto w-full rounded-xl px-4 py-3 text-sm font-medium shadow-lg',
            t.type === 'error' ? 'bg-red-600 text-white'
              : t.type === 'success' ? 'bg-emerald-600 text-white'
              : 'bg-gray-900 text-white',
          ]"
        >
          {{ t.message }}
        </div>
      </transition-group>
    </div>
  </div>
</template>

<style>
.fade-enter-active, .fade-leave-active { transition: opacity 0.15s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
.toast-enter-active, .toast-leave-active { transition: all 0.25s ease; }
.toast-enter-from, .toast-leave-to { opacity: 0; transform: translateY(-8px); }
</style>
