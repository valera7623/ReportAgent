import { API_BASE } from "./config.js";
import { API_KEY_STORAGE, JWT_STORAGE } from "./config.js";
import { logout, state } from "./state.js";
import { navigate } from "./router.js";
import { showModal, toast } from "./ui.js";
import { qs } from "./utils.js";

function headers(json = true) {
  const h = {};
  if (json) h["Content-Type"] = "application/json";
  const key = localStorage.getItem(API_KEY_STORAGE);
  if (key) h["X-API-Key"] = key;
  return h;
}

async function showUpgradeModal(message) {
  await showModal({
    title: "Лимит отчётов исчерпан",
    body: `<p>${message || "Оформите подписку, чтобы продолжить генерацию отчётов."}</p>`,
    footer: `
      <button class="btn btn-outline" data-modal-action="false">Закрыть</button>
      <button class="btn" data-modal-action="upgrade">Смотреть тарифы</button>`,
  }).then((action) => {
    if (action === "upgrade") navigate("/pricing");
  });
}

async function handleResponse(res, { skipAuthRedirect = false } = {}) {
  const text = await res.text();
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }

  const detail = data?.detail;
  const detailObj = typeof detail === "object" && detail !== null ? detail : null;
  const serverMsg =
    typeof detail === "string"
      ? detail
      : detailObj?.message
        ? detailObj.message
        : Array.isArray(detail)
          ? detail.map((d) => d.msg || d).join(", ")
          : null;

  if (res.status === 401) {
    if (!skipAuthRedirect) {
      logout();
      navigate("/login");
      throw new Error("Сессия истекла. Войдите снова.");
    }
    throw new Error(serverMsg || "Неверный API-ключ");
  }

  if (res.status === 402) {
    if (!skipAuthRedirect && state.billingEnabled) {
      await showUpgradeModal(serverMsg);
    }
    throw new Error(serverMsg || "Требуется подписка");
  }

  if (res.status === 204) return null;

  if (!res.ok) {
    throw new Error(serverMsg || res.statusText || `HTTP ${res.status}`);
  }
  return data;
}

export async function api(path, options = {}) {
  const { skipAuthRedirect = false, ...fetchOptions } = options;
  const url = `${API_BASE}${path}`;
  const res = await fetch(url, {
    ...fetchOptions,
    headers: { ...headers(!(fetchOptions.body instanceof FormData)), ...fetchOptions.headers },
  });
  return handleResponse(res, { skipAuthRedirect });
}

export const dashboardApi = {
  stats: (opts = {}) => api("/api/dashboard/stats", opts),
};

export const paymentsApi = {
  config: (opts = {}) => api("/api/payments/config", opts),
  prices: (opts = {}) => api("/api/payments/prices", opts),
  subscription: (opts = {}) => api("/api/payments/subscription", opts),
  createCheckout: (body, opts = {}) =>
    api("/api/payments/create-checkout", {
      method: "POST",
      body: JSON.stringify(body),
      ...opts,
    }),
  cancelSubscription: (opts = {}) =>
    api("/api/payments/cancel-subscription", { method: "POST", ...opts }),
  /** YooKassa (legacy / RU) */
  yookassaSubscription: (opts = {}) => api("/api/payments/yookassa/subscription", opts),
  yookassaCreate: (body, opts = {}) =>
    api("/api/payments/yookassa/create", {
      method: "POST",
      body: JSON.stringify(body),
      ...opts,
    }),
  yookassaStatus: (id, opts = {}) => api(`/api/payments/yookassa/status/${id}`, opts),
};

export const reportsApi = {
  list: (params) => api(`/api/reports${qs(params)}`),
  delete: (id) => api(`/api/reports/${id}`, { method: "DELETE" }),
  retry: (formData) =>
    api("/generate_report", { method: "POST", body: formData, headers: headers(false) }),
};

export const previewApi = {
  create: (formData) =>
    api("/api/reports/preview", { method: "POST", body: formData, headers: headers(false) }),
  get: (previewId) => api(`/api/reports/preview/${previewId}`),
  jobStatus: (jobId) => api(`/api/reports/preview/status/${jobId}`),
  confirm: (body) =>
    api("/api/reports/preview/confirm", { method: "POST", body: JSON.stringify(body) }),
  regenerateChart: (body) =>
    api("/api/reports/preview/regenerate-chart", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};

export const aiApi = {
  analyze: (formData) =>
    api("/api/reports/analyze", { method: "POST", body: formData, headers: headers(false) }),
  generateWithAi: (formData) =>
    api("/api/reports/generate-with-ai", {
      method: "POST",
      body: formData,
      headers: headers(false),
    }),
};

export const keysApi = {
  list: () => api("/api/keys"),
  generate: (body) => {
    const jwt = localStorage.getItem(JWT_STORAGE);
    const headers = { "Content-Type": "application/json" };
    if (jwt) {
      headers.Authorization = `Bearer ${jwt}`;
    }
    return api("/api/keys/generate", {
      method: "POST",
      body: JSON.stringify(body),
      headers,
      skipAuthRedirect: !!jwt,
    });
  },
  revoke: (id) => api(`/api/keys/${id}`, { method: "DELETE" }),
  rotate: (id, body) =>
    api(`/api/keys/${id}/rotate`, { method: "POST", body: JSON.stringify(body || {}) }),
  rename: (id, name) =>
    api(`/api/keys/${id}/rename`, { method: "PUT", body: JSON.stringify({ name }) }),
};

export const webhooksApi = {
  list: () => api("/api/webhooks"),
  register: (body) => api("/api/webhooks/register", { method: "POST", body: JSON.stringify(body) }),
  update: (id, body) => api(`/api/webhooks/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  delete: (id) => api(`/api/webhooks/${id}`, { method: "DELETE" }),
};

export const preferencesApi = {
  get: () => api("/api/preferences"),
  update: (body) => api("/api/preferences", { method: "PUT", body: JSON.stringify(body) }),
};

export const adminApi = {
  checkAdmin: (opts = {}) => api("/admin/health/all", opts),
  users: (params) => api(`/admin/users${qs(params)}`),
  user: (id) => api(`/admin/users/${id}`),
  block: (id) => api(`/admin/users/${id}/block`, { method: "POST" }),
  unblock: (id) => api(`/admin/users/${id}/unblock`, { method: "POST" }),
  deleteUser: (id) => api(`/admin/users/${id}`, { method: "DELETE" }),
  health: () => api("/admin/health/all"),
  system: () => api("/admin/health/system"),
  celery: () => api("/admin/celery/status"),
  purgeQueue: () => api("/admin/celery/purge-queue", { method: "POST" }),
  restartWorker: () => api("/admin/celery/restart-worker", { method: "POST" }),
  selfHealing: () => api("/admin/self-healing/stats"),
  seedFixes: () => api("/admin/self-healing/seed-fixes?overwrite=true", { method: "POST" }),
  rebuildIndex: () => api("/admin/self-healing/rebuild-index", { method: "POST" }),
  deleteFix: (id) => api(`/admin/self-healing/fixes/${id}`, { method: "DELETE" }),
  stripeSubscriptions: (params) => api(`/admin/payments/subscriptions${qs(params)}`),
  stripeRevenue: (params) => api(`/admin/payments/revenue${qs(params)}`),
  stripeRefund: (id) => api(`/admin/payments/refund/${id}`, { method: "POST" }),
  payments: (params) => api(`/admin/payments/yookassa${qs(params)}`),
  payment: (id) => api(`/admin/payments/yookassa/${id}`),
  refundPayment: (id) => api(`/admin/payments/yookassa/refund/${id}`, { method: "POST" }),
  logs: (params) => api(`/admin/logs${qs(params)}`),
  downloadLogs: async (params) => {
    const url = `${API_BASE}/admin/logs/download${qs(params)}`;
    const key = localStorage.getItem(API_KEY_STORAGE);
    const res = await fetch(url, { headers: key ? { "X-API-Key": key } : {} });
    if (!res.ok) throw new Error("Ошибка скачивания");
    return res.blob();
  },
  async *streamLogs(level) {
    const url = `${API_BASE}/admin/logs/stream${qs({ level: level || undefined })}`;
    const key = localStorage.getItem(API_KEY_STORAGE);
    const res = await fetch(url, { headers: key ? { "X-API-Key": key } : {} });
    if (!res.ok || !res.body) throw new Error(`Stream failed: ${res.status}`);
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop() ?? "";
      for (const part of parts) {
        const line = part.split("\n").find((l) => l.startsWith("data: "));
        if (line) yield JSON.parse(line.slice(6));
      }
    }
  },
};

export function onError(err) {
  toast(err.message || "Ошибка", "error");
}
