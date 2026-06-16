export function formatDate(value) {
  if (!value) return "—";
  try {
    const d = new Date(String(value).replace(" ", "T"));
    return d.toLocaleString("ru-RU", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return value;
  }
}

export function truncateId(id, len = 8) {
  if (!id) return "—";
  return id.length <= len ? id : `${id.slice(0, len)}…`;
}

export function formatPercent(n) {
  return `${Number(n).toFixed(1)}%`;
}

export function formatDuration(seconds) {
  if (seconds == null || Number.isNaN(seconds)) return "—";
  if (seconds < 60) return `${Number(seconds).toFixed(1)} с`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}м ${s}с`;
}

export function formatBytes(bytes) {
  if (bytes == null) return "—";
  const u = ["B", "KB", "MB", "GB"];
  let v = bytes;
  let i = 0;
  while (v >= 1024 && i < u.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(1)} ${u[i]}`;
}

export function statusClass(status) {
  const s = (status || "").toUpperCase();
  if (s === "SUCCESS") return "badge-success";
  if (s === "FAILURE" || s === "REVOKED") return "badge-danger";
  if (s === "PENDING" || s === "STARTED") return "badge-warn";
  return "badge-muted";
}

export function paymentStatusClass(status) {
  const s = (status || "").toLowerCase();
  if (s === "succeeded") return "badge-success";
  if (s === "canceled" || s === "cancelled") return "badge-danger";
  if (s === "pending" || s === "waiting_for_capture") return "badge-warn";
  return "badge-muted";
}

export function formatRubles(kopeks) {
  if (kopeks == null || Number.isNaN(Number(kopeks))) return "—";
  return `${(Number(kopeks) / 100).toFixed(2)} ₽`;
}

export function formatUsdCents(cents) {
  if (cents == null || Number.isNaN(Number(cents))) return "—";
  return `$${(Number(cents) / 100).toFixed(2)}`;
}

const PLAN_LABELS = {
  freemium: "Freemium",
  premium: "Premium",
  premium_monthly: "Premium (месяц)",
  premium_yearly: "Premium (год)",
  enterprise: "Enterprise",
};

export function planLabel(planType) {
  return PLAN_LABELS[planType] || planType || "—";
}

export function healthDot(status) {
  if (status === "ok") return "dot-ok";
  if (status === "degraded" || status === "disabled") return "dot-warn";
  return "dot-bad";
}

export function escapeHtml(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export function qs(params) {
  const p = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v != null && v !== "") p.set(k, String(v));
  });
  const s = p.toString();
  return s ? `?${s}` : "";
}
