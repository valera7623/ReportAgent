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
  { href: "/help/", label: "Документы", icon: "📚", external: true },
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
  if (item.external) {
    return `<a href="${item.href}" class="nav-link" target="_blank" rel="noopener"><span>${item.icon}</span>${item.label}</a>`;
  }
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
      <div class="sidebar-backdrop" data-action="close-sidebar" aria-hidden="true"></div>
      <aside class="sidebar" id="app-sidebar" aria-label="Навигация">
        <div class="sidebar-brand">
          <span>🛡️ ReportAgent</span>
          <button type="button" class="sidebar-close btn-icon" data-action="close-sidebar" aria-label="Закрыть меню">&times;</button>
        </div>
        <nav class="sidebar-nav">
          ${userNav.map((n) => navLink(n, current)).join("")}
          ${adminSection}
        </nav>
      </aside>
      <div class="main">
        <header class="header">
          <button type="button" class="menu-btn" data-action="toggle-sidebar" aria-label="Открыть меню" aria-expanded="${state.sidebarOpen ? "true" : "false"}" aria-controls="app-sidebar">
            <span class="menu-btn-bar" aria-hidden="true"></span>
            <span class="menu-btn-bar" aria-hidden="true"></span>
            <span class="menu-btn-bar" aria-hidden="true"></span>
          </button>
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
  bindSidebar(root);
  root.querySelector('[data-action="toggle-theme"]')?.addEventListener("click", () => toggleTheme());
  root.querySelector('[data-action="logout"]')?.addEventListener("click", () => {
    logout();
    navigate("/login");
  });
  bindExtra?.(root);
}

function bindSidebar(root) {
  const layout = root.querySelector(".layout");
  const menuBtn = root.querySelector(".menu-btn");

  const applySidebar = (open) => {
    layout?.classList.toggle("sidebar-open", open);
    menuBtn?.setAttribute("aria-expanded", open ? "true" : "false");
    document.body.classList.toggle("sidebar-open-body", open);
  };

  applySidebar(state.sidebarOpen);

  const setSidebar = (open) => {
    toggleSidebar(open);
    applySidebar(state.sidebarOpen);
  };

  root.querySelector('[data-action="toggle-sidebar"]')?.addEventListener("click", () => setSidebar());
  root.querySelectorAll('[data-action="close-sidebar"]').forEach((el) => {
    el.addEventListener("click", () => setSidebar(false));
  });

  root.querySelectorAll(".sidebar-nav .nav-link").forEach((link) => {
    link.addEventListener("click", () => {
      if (window.matchMedia("(max-width: 1023px)").matches) setSidebar(false);
    });
  });
}

export function initLayoutSubscription(renderFn) {
  subscribe(() => {
    const hash = location.hash.replace(/^#/, "");
    if (hash && hash !== "/login") renderFn();
  });
}
