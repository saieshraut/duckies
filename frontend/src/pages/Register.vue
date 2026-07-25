<script setup>
import { ref } from "vue";
import { useRouter, RouterLink } from "vue-router";
import { session } from "@/stores/session";
import { toast } from "@/lib/toast";
import UiButton from "@/components/UiButton.vue";

const router = useRouter();
const form = ref({ full_name: "", email: "", mobile: "", password: "" });
const consent = ref(false);
const loading = ref(false);

async function submit() {
  if (!consent.value) {
    toast("Please accept the terms to continue", "error");
    return;
  }
  loading.value = true;
  try {
    await session.register({ ...form.value, consent: 1 });
    toast("Welcome to Duckie's!", "success");
    router.replace("/wallet");
  } catch (e) {
    toast(e.message || "Registration failed", "error");
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="flex min-h-full flex-col justify-center px-6 py-10">
    <div class="mb-6 text-center">
      <div class="mx-auto mb-3 flex h-16 w-16 items-center justify-center rounded-2xl bg-duck-500 text-3xl shadow-lg">🦆</div>
      <h1 class="text-2xl font-extrabold text-gray-900">Join Duckie's</h1>
      <p class="mt-1 text-sm text-gray-500">Create your wallet account</p>
    </div>

    <form class="space-y-4" @submit.prevent="submit">
      <input v-model="form.full_name" placeholder="Full name" required
        class="w-full rounded-xl border border-gray-200 px-4 py-3 text-sm focus:border-duck-400 focus:ring-2 focus:ring-duck-100" />
      <input v-model="form.email" type="email" placeholder="Email" autocomplete="email" required
        class="w-full rounded-xl border border-gray-200 px-4 py-3 text-sm focus:border-duck-400 focus:ring-2 focus:ring-duck-100" />
      <input v-model="form.mobile" type="tel" placeholder="Mobile number" autocomplete="tel" required
        class="w-full rounded-xl border border-gray-200 px-4 py-3 text-sm focus:border-duck-400 focus:ring-2 focus:ring-duck-100" />
      <input v-model="form.password" type="password" placeholder="Password (min 8 chars)" autocomplete="new-password" required minlength="8"
        class="w-full rounded-xl border border-gray-200 px-4 py-3 text-sm focus:border-duck-400 focus:ring-2 focus:ring-duck-100" />

      <label class="flex items-start gap-2 text-xs text-gray-600">
        <input v-model="consent" type="checkbox" class="mt-0.5 h-4 w-4 rounded border-gray-300 text-duck-500 focus:ring-duck-400" />
        <span>I agree to the Terms &amp; Conditions and Privacy Notice. I understand wallet balances are for use at Duckie's and bonus credit is promotional and non-refundable.</span>
      </label>

      <UiButton :loading="loading" type="submit">Create account</UiButton>
    </form>

    <p class="mt-6 text-center text-sm text-gray-500">
      Already have an account?
      <RouterLink to="/login" class="font-semibold text-duck-600">Sign in</RouterLink>
    </p>
  </div>
</template>
