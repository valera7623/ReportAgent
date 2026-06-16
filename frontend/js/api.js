import { API_BASE } from "./config.js";
import { API_KEY_STORAGE } from "./config.js";
import { logout } from "./state.js";
import { navigate } from "./router.js";
import { toast } from "./ui.js";
import { qs } from "./utils.js";

function headers(json = true) {
  const h = {};
  if (json) h["Content-Type"] = "application/json";
  const key = localStorage.getItem(API_KEY_STORAGE);
  if (key) h["X-API-Key"] = key;
  return h;
}

async function handleResponse(res) {
  if (res.status === 401) {
    logout();
    navigate("/login");
    throw new Error("Сессия истекла. Войдите снова.");
  }
  if (res.status === 204) return null;
  const text = await res.text();
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }
  if (!res.ok) {
    const detail = data?.detail;
    const msg =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail.map((d) => d.msg || d).join(", ")
          : res.statusText;
    throw new Error(msg || `HTTP ${res.status}`);
  }
  return data;
}

export async function api(path, options = {}) {
  const url = `${API_BASE}${path}`;
  const res = await fetch(url, {
    ...options,
    headers: { ...headers(!(options.body instanceof FormData)), ...options.headers },
  });
  return handleResponse(res);
}

export const dashboardApi = {
  stats: () => api("/api/dashboard/stats"),
};

export const reportsApi = {
  list: (params) => api(`/api/reports${qs(params)}`),
  delete: (id) => api(`/api/reports/${id}`, { method: "DELETE" }),
  retry: (formData) =>
    api("/generate_report", { method: "POST", body: formData, headers: headers(false) }),
};

export const keysApi = {
  list: () => api("/api/keys"),
  generate: (body) => api("/api/keys/generate", { method: "POST", body: JSON.stringify(body) }),
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
  checkAdmin: () => api("/admin/health/all"),
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
