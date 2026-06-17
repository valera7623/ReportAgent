import { state, subscribe, toggleSidebar, toggleTheme, logout } from "./state.js";
import { navigate } from "./router.js";
import { escapeHtml } from "./utils.js";

const userNavAll = [
  { path: "/dashboard", label: "Дашборд", icon: "📊" },
  { path: "/reports", label: "Отчёты", icon: "📄" },
  { path: "/keys", label: "API-ключи", icon: "🔑" },
  { path: "/webhooks", label: "Вебхуки", icon: "🔗" },
  { path: "/pricing", label: "Тарифы", icon: "💳", billing: true },
  { path: "/subscription", label: "Подписка", icon: "⭐", billing: true },
  { path: "/preferences", label: "Настройки", icon: "⚙️" },
];

const adminNav = [
  { path: "/admin/users", label: "Пользователи", icon: "👥" },
  { path: "/admin/payments", label: "Платежи", icon: "💳" },
  { path: "/admin/health", label: "Здоровье", icon: "💚" },
  { path: "/admin/celery", label: "Celery", icon: "📋" },
  { path: "/admin/self-healing", label: "Self-Healing", icon: "🔧" },
  { path: "/admin/logs", label: "Логи", icon: "📝" },
];

function navLink(item, current) {
  const active = current === item.path ? "active" : "";
  return `<a href="#${item.path}" class="nav-link ${active}"><span>${item.icon}</span>${item.label}</a>`;
}

export function renderShell(contentHtml, title = "") {
  const hash = location.hash.replace(/^#/, "") || "/dashboard";
  const current = hash.split("?")[0];
  const prefix = state.apiKey ? `${state.apiKey.slice(0, 8)}…` : "—";
  const userNav = userNavAll.filter((n) => state.billingEnabled || !n.billing);

  const adminSection = state.isAdmin
    ? `<div class="nav-section">Админ</div>${adminNav.map((n) => navLink(n, current)).join("")}`
    : "";

  return `
    <div class="layout ${state.sidebarOpen ? "sidebar-open" : ""}">
      <div class="sidebar-backdrop" data-action="close-sidebar"></div>
      <aside class="sidebar">
        <div class="sidebar-brand">🛡️ ReportAgent</div>
        <nav class="sidebar-nav">
          ${userNav.map((n) => navLink(n, current)).join("")}
          ${adminSection}
        </nav>
      </aside>
      <div class="main">
        <header class="header">
          <button type="button" class="btn-icon menu-btn" data-action="toggle-sidebar">☰</button>
          <p class="header-title" role="heading" aria-level="2">${escapeHtml(title)}</p>
          <div class="header-actions">
            <span class="key-badge" title="Текущий ключ">🔑 ${escapeHtml(prefix)}${state.isAdmin ? ' <span class="badge">Admin</span>' : ""}</span>
            <button type="button" class="btn-icon" data-action="toggle-theme" title="Тема">${state.theme === "dark" ? "☀️" : "🌙"}</button>
            <button type="button" class="btn btn-outline btn-sm" data-action="logout">Выход</button>
          </div>
        </header>
        <main class="content">${contentHtml}</main>
      </div>
    </div>`;
}

export function mountShell(root, title, contentHtml, bindExtra) {
  root.innerHTML = renderShell(contentHtml, title);
  root.querySelector('[data-action="toggle-sidebar"]')?.addEventListener("click", () => toggleSidebar());
  root.querySelector('[data-action="close-sidebar"]')?.addEventListener("click", () => toggleSidebar(false));
  root.querySelector('[data-action="toggle-theme"]')?.addEventListener("click", () => toggleTheme());
  root.querySelector('[data-action="logout"]')?.addEventListener("click", () => {
    logout();
    navigate("/login");
  });
  bindExtra?.(root);
}

export function initLayoutSubscription(renderFn) {
  subscribe(() => {
    const hash = location.hash.replace(/^#/, "");
    if (hash && hash !== "/login") renderFn();
  });
}
