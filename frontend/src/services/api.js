const TOKEN_KEY = "aifp_token";

export const tokenStore = {
  get: () => { try { return sessionStorage.getItem(TOKEN_KEY); } catch { return null; } },
  set: (t) => { try { sessionStorage.setItem(TOKEN_KEY, t); } catch { /* ignore */ } },
  clear: () => { try { sessionStorage.removeItem(TOKEN_KEY); } catch { /* ignore */ } },
};

export class ApiError extends Error {
  constructor(message, status, details) {
    super(message);
    this.status = status;
    this.details = details;
  }
}

export async function api(path, { method = "GET", body } = {}) {
  const headers = { "Content-Type": "application/json" };
  const token = tokenStore.get();
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`/api/v1${path}`, { method, headers, body: body ? JSON.stringify(body) : undefined });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(data.error || "Request failed", res.status, data.details);
  return data;
}

export const authApi = {
  register: (b) => api("/auth/register", { method: "POST", body: b }),
  login: (b) => api("/auth/login", { method: "POST", body: b }),
  logout: () => api("/auth/logout", { method: "POST" }),
  me: () => api("/auth/me"),
  forgot: (email) => api("/auth/forgot-password", { method: "POST", body: { email } }),
  reset: (token, password) => api("/auth/reset-password", { method: "POST", body: { token, password } }),
  verify: (token) => api("/auth/verify-email", { method: "POST", body: { token } }),
  resendVerification: () => api("/auth/resend-verification", { method: "POST" }),
};

export const profileApi = {
  update: (b) => api("/profile", { method: "PUT", body: b }),
  getFashion: () => api("/profile/fashion"),
  saveFashion: (b) => api("/profile/fashion", { method: "PUT", body: b }),
  deleteFashion: () => api("/profile/fashion", { method: "DELETE" }),
};

const qs = (o) => {
  const p = new URLSearchParams();
  Object.entries(o).forEach(([k, v]) => [].concat(v ?? []).forEach((x) => x !== "" && x != null && p.append(k, x)));
  const s = p.toString();
  return s ? `?${s}` : "";
};

export const shopApi = {
  categories: () => api("/categories"),
  filters: () => api("/filters"),
  products: (params) => api(`/products${qs(params)}`),
  product: (id) => api(`/products/${id}`),
  wishlist: () => api("/wishlist"),
  wishAdd: (id) => api(`/wishlist/${id}`, { method: "PUT" }),
  wishRemove: (id) => api(`/wishlist/${id}`, { method: "DELETE" }),
  cart: () => api("/cart"),
  cartAdd: (variant_id, quantity = 1) => api("/cart/items", { method: "POST", body: { variant_id, quantity } }),
  cartSet: (id, quantity) => api(`/cart/items/${id}`, { method: "PATCH", body: { quantity } }),
  cartRemove: (id) => api(`/cart/items/${id}`, { method: "DELETE" }),
  addresses: () => api("/addresses"),
  addressCreate: (b) => api("/addresses", { method: "POST", body: b }),
  checkout: (address_id) => api("/checkout", { method: "POST", body: { address_id } }),
  orders: () => api("/orders"),
  order: (id) => api(`/orders/${id}`),
  cancelOrder: (id) => api(`/orders/${id}/cancel`, { method: "POST" }),
  payRetry: (order_id) => api("/payments/create-order", { method: "POST", body: { order_id } }),
  mockPay: (order_id, outcome) => api("/payments/mock/pay", { method: "POST", body: { order_id, outcome } }),
};

export const walletApi = {
  wallet: () => api("/wallet"),
  transactions: (params) => api(`/wallet/transactions${qs(params)}`),
  costs: () => api("/wallet/credit-costs"),
  quote: (service) => api("/wallet/transactions/quote", { method: "POST", body: { service } }),
  packs: () => api("/wallet/packs"),
  buyPack: (id) => api(`/wallet/packs/${id}/purchase`, { method: "POST" }),
  plans: () => api("/subscriptions/plans"),
  subscribe: (plan_id) => api("/subscriptions/checkout", { method: "POST", body: { plan_id } }),
  mySubscription: () => api("/subscriptions/me"),
  cancelSubscription: () => api("/subscriptions/cancel", { method: "POST" }),
  mockPay: (provider_order_id, outcome) => api("/payments/mock/pay", { method: "POST", body: { provider_order_id, outcome } }),
};

export const stylistApi = {
  list: () => api("/stylists"),
  get: (id) => api(`/stylists/${id}`),
  slots: (id) => api(`/stylists/${id}/availability`),
  quote: (slot_id) => api("/consultations/quote", { method: "POST", body: { slot_id } }),
  book: (slot_id, notes) => api("/consultations", { method: "POST", body: { slot_id, notes: notes || null } }),
  consultations: (params) => api(`/consultations${qs(params || {})}`),
  consultation: (id) => api(`/consultations/${id}`),
  act: (id, action) => api(`/consultations/${id}/${action}`, { method: "POST" }),
  messages: (id, after = 0) => api(`/consultations/${id}/messages?after=${after}`),
  send: (id, text) => api(`/consultations/${id}/messages`, { method: "POST", body: { text } }),
  myProfile: () => api("/stylist/profile"),
  saveProfile: (b) => api("/stylist/profile", { method: "PUT", body: b }),
  mySlots: () => api("/stylist/availability"),
  addSlot: (start_at, duration_minutes) => api("/stylist/availability", { method: "POST", body: { start_at, duration_minutes } }),
  deleteSlot: (id) => api(`/stylist/availability/${id}`, { method: "DELETE" }),
  earnings: () => api("/stylist/earnings"),
};

export const notifyApi = {
  list: () => api("/notifications"),
  markRead: (ids) => api("/notifications/read", { method: "POST", body: ids ? { ids } : {} }),
};

export const rewardsApi = {
  balance: () => api("/rewards/balance"),
  transactions: (params) => api(`/rewards/transactions${qs(params || {})}`),
  offers: () => api("/rewards/offers"),
  redeem: (offer_id) => api("/rewards/redeem", { method: "POST", body: { offer_id } }),
};

export const aiApi = {
  chat: (message, session_id) => api("/ai/chat", { method: "POST", body: { message, ...(session_id ? { session_id } : {}) } }),
  sessions: () => api("/ai/sessions"),
  session: (id) => api(`/ai/sessions/${id}`),
  remove: (id) => api(`/ai/sessions/${id}`, { method: "DELETE" }),
  recommendations: () => api("/recommendations"),
};

export const adminApi = {
  stylists: () => api("/admin/stylists"),
  createStylist: (b) => api("/admin/stylists", { method: "POST", body: b }),
  updateStylist: (id, b) => api(`/admin/stylists/${id}`, { method: "PUT", body: b }),
  section: (key) => api(`/admin/settings/${key}`),
  saveSection: (key, b) => api(`/admin/settings/${key}`, { method: "PUT", body: b }),
  offers: () => api("/admin/reward-offers"),
  saveOffer: (id, b) => (id ? api(`/admin/reward-offers/${id}`, { method: "PUT", body: b }) : api("/admin/reward-offers", { method: "POST", body: b })),
  creditSettings: () => api("/admin/settings/credits"),
  saveCreditSettings: (b) => api("/admin/settings/credits", { method: "PUT", body: b }),
  packs: () => api("/admin/credit-packs"),
  savePack: (id, b) => (id ? api(`/admin/credit-packs/${id}`, { method: "PUT", body: b }) : api("/admin/credit-packs", { method: "POST", body: b })),
  plans: () => api("/admin/plans"),
  savePlan: (id, b) => (id ? api(`/admin/plans/${id}`, { method: "PUT", body: b }) : api("/admin/plans", { method: "POST", body: b })),
  userWallet: (id) => api(`/admin/users/${id}/wallet`),
  adjust: (id, b) => api(`/admin/users/${id}/wallet/adjust`, { method: "POST", body: b }),
  users: (params) => api(`/admin/users${qs(params || {})}`),
  setUserActive: (id, is_active) => api(`/admin/users/${id}`, { method: "PATCH", body: { is_active } }),
  audit: (params) => api(`/admin/audit-logs${qs(params || {})}`),
  dashboard: (days) => api(`/admin/dashboard?days=${days}`),
  inventory: (params) => api(`/admin/inventory${qs(params || {})}`),
  setStock: (variantId, stock_quantity) => api(`/admin/variants/${variantId}/stock`, { method: "PATCH", body: { stock_quantity } }),
  categories: () => api("/admin/categories"),
  saveCategory: (id, b) => (id ? api(`/admin/categories/${id}`, { method: "PUT", body: b }) : api("/admin/categories", { method: "POST", body: b })),
  refund: (orderId, b) => api(`/admin/orders/${orderId}/refund`, { method: "POST", body: b }),
  refunds: () => api("/admin/refunds"),
  subscriptions: () => api("/admin/subscriptions"),
  consultationsAll: (status) => api(`/admin/consultations${qs({ status })}`),
  products: () => api("/admin/products"),
  product: (id) => api(`/admin/products/${id}`),
  createProduct: (b) => api("/admin/products", { method: "POST", body: b }),
  updateProduct: (id, b) => api(`/admin/products/${id}`, { method: "PUT", body: b }),
  archiveProduct: (id) => api(`/admin/products/${id}`, { method: "DELETE" }),
  orders: () => api("/admin/orders"),
  setStatus: (id, order_status) => api(`/admin/orders/${id}/status`, { method: "PATCH", body: { order_status } }),
};

/** Download an authenticated CSV (a plain link can't send the bearer token). */
export async function downloadCsv(name, days) {
  const res = await fetch(`/api/v1/admin/reports/${name}.csv?days=${days}`, { headers: { Authorization: `Bearer ${tokenStore.get()}` } });
  if (!res.ok) throw new ApiError("Download failed", res.status);
  const url = URL.createObjectURL(await res.blob());
  const a = Object.assign(document.createElement("a"), { href: url, download: `${name}-${days}d.csv` });
  document.body.appendChild(a); a.click(); a.remove();
  URL.revokeObjectURL(url);
}

export const privacyApi = {
  exportData: async () => {
    const res = await fetch("/api/v1/profile/export", { headers: { Authorization: `Bearer ${tokenStore.get()}` } });
    if (!res.ok) throw new ApiError("Export failed", res.status);
    const url = URL.createObjectURL(await res.blob());
    const a = Object.assign(document.createElement("a"), { href: url, download: "my-data.json" });
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
  },
  deleteAccount: (password, confirm) => api("/profile/delete-account", { method: "POST", body: { password, confirm } }),
};
