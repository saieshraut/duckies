import { reactive } from "vue";
import { api, auth } from "@/lib/api";

export const session = reactive({
  loading: true,
  user: null, // profile object or null
  error: null,

  get isLoggedIn() {
    return !!this.user;
  },

  async load() {
    this.loading = true;
    try {
      this.user = await api.profile();
    } catch {
      this.user = null; // not logged in / no customer
    } finally {
      this.loading = false;
    }
  },

  async refreshBalance() {
    if (!this.user) return;
    const b = await api.balance();
    this.user.wallet_balance = b.balance;
    this.user.cash_balance = b.cash_balance;
    this.user.bonus_balance = b.bonus_balance;
  },

  async login(usr, pwd) {
    await auth.login(usr, pwd);
    await this.load();
  },

  async register(payload) {
    await auth.register(payload);
    await this.load();
  },

  async logout() {
    await auth.logout();
    this.user = null;
    window.location.href = "/cafe";
  },
});
