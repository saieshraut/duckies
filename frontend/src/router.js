import { createRouter, createWebHistory } from "vue-router";
import { session } from "@/stores/session";

const routes = [
  { path: "/", name: "home", component: () => import("@/pages/Home.vue") },
  { path: "/login", name: "login", component: () => import("@/pages/Login.vue"), meta: { guest: true } },
  { path: "/register", name: "register", component: () => import("@/pages/Register.vue"), meta: { guest: true } },
  { path: "/wallet", name: "wallet", component: () => import("@/pages/Wallet.vue"), meta: { auth: true } },
  { path: "/recharge", name: "recharge", component: () => import("@/pages/Recharge.vue"), meta: { auth: true } },
  { path: "/events", name: "events", component: () => import("@/pages/Events.vue") },
  { path: "/events/:name", name: "event", component: () => import("@/pages/EventDetail.vue") },
  { path: "/bookings", name: "bookings", component: () => import("@/pages/Bookings.vue"), meta: { auth: true } },
  { path: "/menu", name: "menu", component: () => import("@/pages/Menu.vue") },
  { path: "/history", name: "history", component: () => import("@/pages/History.vue"), meta: { auth: true } },
  { path: "/:pathMatch(.*)*", redirect: "/" },
];

const router = createRouter({
  history: createWebHistory("/cafe"),
  routes,
  scrollBehavior: () => ({ top: 0 }),
});

router.beforeEach(async (to) => {
  if (session.loading) await session.load();
  if (to.meta.auth && !session.isLoggedIn) {
    return { name: "login", query: { redirect: to.fullPath } };
  }
  if (to.meta.guest && session.isLoggedIn) {
    return { name: "wallet" };
  }
});

export default router;
