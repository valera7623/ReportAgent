import { initState, state, setIsAdmin } from "./state.js";
import { initRouter, registerRoute, renderRoute } from "./router.js";
import { adminApi, dashboardApi } from "./api.js";
import { renderLogin } from "./pages/login.js";
import { renderDashboard } from "./pages/dashboard.js";
import { renderReports } from "./pages/reports.js";
import { renderKeys } from "./pages/keys.js";
import { renderWebhooks } from "./pages/webhooks.js";
import { renderPreferences } from "./pages/preferences.js";
import {
  renderAdminUsers,
  renderAdminUserDetail,
  renderAdminHealth,
  renderAdminCelery,
  renderAdminSelfHealing,
  renderAdminLogs,
} from "./pages/admin.js";

const app = document.getElementById("app");

async function boot() {
  initState();
  initRouter();

  registerRoute("/login", () => renderLogin(app));
  registerRoute("/dashboard", () => renderDashboard(app));
  registerRoute("/reports", () => renderReports(app));
  registerRoute("/keys", () => renderKeys(app));
  registerRoute("/webhooks", () => renderWebhooks(app));
  registerRoute("/preferences", () => renderPreferences(app));
  registerRoute("/admin/users", () => renderAdminUsers(app));
  registerRoute("/admin/users/:id", (id) => renderAdminUserDetail(app, id));
  registerRoute("/admin/health", () => renderAdminHealth(app));
  registerRoute("/admin/celery", () => renderAdminCelery(app));
  registerRoute("/admin/self-healing", () => renderAdminSelfHealing(app));
  registerRoute("/admin/logs", () => renderAdminLogs(app));

  if (state.isAuthenticated) {
    let isAdmin = false;
    let isUser = false;
    try {
      await adminApi.checkAdmin({ skipAuthRedirect: true });
      isAdmin = true;
      setIsAdmin(true);
    } catch {
      setIsAdmin(false);
    }
    try {
      await dashboardApi.stats({ skipAuthRedirect: true });
      isUser = true;
    } catch {
      isUser = false;
    }
    state.isAdminOnly = isAdmin && !isUser;
  }

  if (!location.hash || location.hash === "#") {
    if (!state.isAuthenticated) {
      location.hash = "#/login";
    } else if (state.isAdminOnly) {
      location.hash = "#/admin/health";
    } else {
      location.hash = "#/dashboard";
    }
  }

  await renderRoute();
}

boot();
