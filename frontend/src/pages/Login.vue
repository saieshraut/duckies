<script setup>
import { ref } from "vue";
import { useRouter, useRoute, RouterLink } from "vue-router";
import { session } from "@/stores/session";
import { toast } from "@/lib/toast";
import UiButton from "@/components/UiButton.vue";

const router = useRouter();
const route = useRoute();
const usr = ref("");
const pwd = ref("");
const loading = ref(false);

async function submit() {
  if (!usr.value || !pwd.value) return;
  loading.value = true;
  try {
    await session.login(usr.value, pwd.value);
    router.replace(route.query.redirect || "/wallet");
  } catch (e) {
    toast(e.message || "Login failed", "error");
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="flex min-h-full flex-col justify-center px-6 py-12">
    <div class="mb-8 text-center">
      <div class="mx-auto mb-3 flex h-16 w-16 items-center justify-center rounded-2xl bg-duck-500 text-3xl shadow-lg">🦆</div>
      <h1 class="text-2xl font-extrabold text-gray-900">Welcome back</h1>
      <p class="mt-1 text-sm text-gray-500">Sign in to Duckie's</p>
    </div>

    <form class="space-y-4" @submit.prevent="submit">
      <div>
        <label class="mb-1 block text-sm font-medium text-gray-700">Email</label>
        <input v-model="usr" type="email" autocomplete="email" required
          class="w-full rounded-xl border border-gray-200 px-4 py-3 text-sm focus:border-duck-400 focus:ring-2 focus:ring-duck-100" />
      </div>
      <div>
        <label class="mb-1 block text-sm font-medium text-gray-700">Password</label>
        <input v-model="pwd" type="password" autocomplete="current-password" required
          class="w-full rounded-xl border border-gray-200 px-4 py-3 text-sm focus:border-duck-400 focus:ring-2 focus:ring-duck-100" />
      </div>
      <UiButton :loading="loading" type="submit">Sign in</UiButton>
    </form>

    <p class="mt-6 text-center text-sm text-gray-500">
      New here?
      <RouterLink to="/register" class="font-semibold text-duck-600">Create an account</RouterLink>
    </p>
  </div>
</template>
