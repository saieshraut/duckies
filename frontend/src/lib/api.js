// Thin wrapper over Frappe's whitelisted method endpoints.
// Session auth is cookie-based; we forward the CSRF token Frappe injects.

function getCSRF() {
  // Frappe sets window.csrf_token on server-rendered pages; fall back to cookie.
  if (window.csrf_token && window.csrf_token !== "None") return window.csrf_token;
  const m = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : "";
}

// Public (guest-readable) methods can be safely retried with a GET, which is
// not subject to CSRF — so they always load even when a stale desk session
// (e.g. logged in as Administrator) causes the POST to fail CSRF with a 400.
const PUBLIC_METHODS = new Set([
  "duckies.api.spaces",
  "duckies.api.events",
  "duckies.api.menu",
  "duckies.api.active_offers",
]);

async function call(method, args = {}, { raw = false } = {}) {
  const res = await fetch(`/api/method/${method}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Frappe-CSRF-Token": getCSRF(),
      Accept: "application/json",
    },
    credentials: "include",
    body: JSON.stringify(args),
  });

  let data = null;
  try {
    data = await res.json();
  } catch {
    /* non-JSON (e.g. 500 HTML page) */
  }

  if (!res.ok) {
    // CSRF/session mismatch (400) on a public method: retry as a GET, which
    // isn't CSRF-protected, so public data still loads.
    if (res.status === 400 && PUBLIC_METHODS.has(method)) {
      try {
        return await callGet(method, args, { raw });
      } catch {
        /* fall through to the original error */
      }
    }
    const msg = extractError(data) || `Request failed (${res.status})`;
    const err = new Error(msg);
    err.status = res.status;
    err.data = data;
    throw err;
  }
  return raw ? data : data?.message;
}

// GET fallback for public, read-only methods.
async function callGet(method, args = {}, { raw = false } = {}) {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(args)) {
    if (v !== undefined && v !== null) qs.set(k, v);
  }
  const url = `/api/method/${method}${qs.toString() ? "?" + qs.toString() : ""}`;
  const res = await fetch(url, {
    method: "GET",
    headers: { Accept: "application/json" },
    credentials: "include",
  });
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const err = new Error(extractError(data) || `Request failed (${res.status})`);
    err.status = res.status;
    throw err;
  }
  return raw ? data : data?.message;
}

// Frappe returns errors as _server_messages (JSON-encoded array) or exception text
function extractError(data) {
  if (!data) return null;
  if (data._server_messages) {
    try {
      const arr = JSON.parse(data._server_messages);
      const first = JSON.parse(arr[0]);
      return stripHtml(first.message || first);
    } catch {
      /* ignore */
    }
  }
  if (data.exception) return stripHtml(data.exception.split(":").slice(1).join(":").trim());
  if (data.message && typeof data.message === "string") return stripHtml(data.message);
  return null;
}

function stripHtml(s) {
  const d = document.createElement("div");
  d.innerHTML = s;
  return (d.textContent || d.innerText || "").trim();
}

// --- Auth (Frappe built-ins) ---------------------------------------------
export const auth = {
  async login(usr, pwd) {
    const res = await fetch("/api/method/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ usr, pwd }),
    });
    if (!res.ok) {
      const d = await res.json().catch(() => null);
      throw new Error(extractError(d) || "Invalid email or password.");
    }
    return res.json();
  },
  logout() {
    return fetch("/api/method/logout", { method: "POST", credentials: "include" });
  },
  register: (payload) => call("duckies.api.register", payload),
};

// --- Duckies API ----------------------------------------------------------
export const api = {
  profile: () => call("duckies.api.get_profile"),
  balance: () => call("duckies.api.balance"),
  transactions: (limit = 20, start = 0) =>
    call("duckies.api.transactions", { limit, start }),
  activeOffers: () => call("duckies.api.active_offers"),

  spaces: () => call("duckies.api.spaces"),
  events: (params = {}) => call("duckies.api.events", params),  bookEvent: (event, seats = 1) =>
    call("duckies.api.book_event", { event, seats }),
  cancelBooking: (booking) => call("duckies.api.cancel_booking", { booking }),
  myBookings: (limit = 20, start = 0) =>
    call("duckies.api.my_bookings", { limit, start }),

  menu: () => call("duckies.api.menu"),
  placeOrder: (items) =>
    call("duckies.api.place_order", { items: JSON.stringify(items) }),

  createRechargeOrder: (amount) =>
    call("duckies.payments.razorpay.create_recharge_order", { amount }),
  requestRefund: (amount, reason) =>
    call("duckies.api.request_refund", { amount, reason }),
};

export { call };
