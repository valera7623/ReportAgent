import { initState, state, setBillingEnabled, setIsAdmin } from "./state.js";
import { initRouter, registerRoute, renderRoute } from "./router.js";
import { adminApi, dashboardApi, paymentsApi } from "./api.js";
import { renderLogin } from "./pages/login.js";
import { renderRegister } from "./pages/register.js";
import { renderVerify } from "./pages/verify.js";
import { renderResetPassword } from "./pages/reset_password.js";
import { renderDashboard } from "./pages/dashboard.js";
import { renderReports } from "./pages/reports.js";
import { renderKeys } from "./pages/keys.js";
import { renderWebhooks } from "./pages/webhooks.js";
import { renderPricing } from "./pages/pricing.js";
import { renderPricingYookassa } from "./pages/pricing_yookassa.js";
import { renderSubscription } from "./pages/subscription.js";
import { renderSuccess } from "./pages/success.js";
import { renderCancel } from "./pages/cancel.js";
import { renderPreferences } from "./pages/preferences.js";
import { renderPaymentSuccess } from "./pages/payment_success.js";
import { renderPaymentCancel } from "./pages/payment_cancel.js";
import {
  renderAdminUsers,
  renderAdminUserDetail,
  renderAdminHealth,
  renderAdminCelery,
  renderAdminSelfHealing,
  renderAdminLogs,
} from "./pages/admin.js";
import { renderAdminPayments } from "./pages/admin_payments.js";

const app = document.getElementById("app");

async function boot() {
  initState();
  initRouter();

  try {
    const billing = await paymentsApi.config({ skipAuthRedirect: true });
    setBillingEnabled(billing?.billing_enabled !== false);
  } catch {
    setBillingEnabled(true);
  }

  registerRoute("/login", () => renderLogin(app));
  registerRoute("/register", () => renderRegister(app));
  registerRoute("/verify", (params) => renderVerify(app, params));
  registerRoute("/reset-password", (params) => renderResetPassword(app, params));
  registerRoute("/reset-password/confirm", (params) => renderResetPassword(app, params));
  registerRoute("/dashboard", () => renderDashboard(app));
  registerRoute("/reports", () => renderReports(app));
  registerRoute("/keys", () => renderKeys(app));
  registerRoute("/webhooks", () => renderWebhooks(app));
  registerRoute("/pricing", () => renderPricing(app));
  registerRoute("/pricing-yookassa", () => renderPricingYookassa(app));
  registerRoute("/subscription", () => renderSubscription(app));
  registerRoute("/success", (params) => renderSuccess(app, params));
  registerRoute("/cancel", () => renderCancel(app));
  registerRoute("/preferences", () => renderPreferences(app));
  registerRoute("/payment/success", (params) => renderPaymentSuccess(app, params));
  registerRoute("/payment/cancel", (params) => renderPaymentCancel(app, params));
  registerRoute("/admin/payments", () => renderAdminPayments(app));
  registerRoute("/admin/users", () => renderAdminUsers(app));
  registerRoute("/admin/users/:id", (id) => renderAdminUserDetail(app, id));
  registerRoute("/admin/health", () => renderAdminHealth(app));
  registerRoute("/admin/celery", () => renderAdminCelery(app));
  registerRoute("/admin/self-healing", () => renderAdminSelfHealing(app));
  registerRoute("/admin/logs", () => renderAdminLogs(app));

  if (state.isAuthenticated) {
    let isAdmin = false;
    let isUser = false;
    const authOpts = { skipAuthRedirect: true };
    try {
      await adminApi.checkAdmin(authOpts);
      isAdmin = true;
      setIsAdmin(true);
    } catch {
      setIsAdmin(false);
    }
    try {
      await dashboardApi.stats(authOpts);
      isUser = true;
    } catch {
      isUser = false;
    }
    state.isAdminOnly = isAdmin && !isUser;
  }

  if (!location.hash || location.hash === "#") {
    if (!state.isAuthenticated) {
      location.hash = "#/login";
    } else if (!state.hasApiKey && state.jwt) {
      location.hash = "#/keys";
    } else if (state.isAdminOnly) {
      location.hash = "#/admin/health";
    } else {
      location.hash = "#/dashboard";
    }
  }

  await renderRoute();
}

boot();
