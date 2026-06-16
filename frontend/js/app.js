import { initState, state, setIsAdmin } from "./state.js";
import { initRouter, registerRoute, renderRoute } from "./router.js";
import { adminApi } from "./api.js";
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
    try {
      await adminApi.checkAdmin();
      setIsAdmin(true);
    } catch {
      setIsAdmin(false);
    }
  }

  if (!location.hash || location.hash === "#") {
    location.hash = state.isAuthenticated ? "#/dashboard" : "#/login";
  }

  await renderRoute();
}

boot();
