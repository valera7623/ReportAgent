import { stopHealthPolling } from "./health-polling.js";
import { updatePageSeo } from "./seo.js";
import { trackPageView } from "./utils/analytics.js";

const routes = {};

const PUBLIC_PATHS = new Set([
  "/login",
  "/register",
  "/verify",
  "/reset-password",
  "/reset-password/confirm",
]);

const JWT_ONLY_PATHS = new Set(["/keys"]);

export function registerRoute(path, handler) {
  routes[path] = handler;
}

function parseHash() {
  const hash = location.hash.replace(/^#/, "") || "/dashboard";
  const [pathPart, query] = hash.split("?");
  const parts = pathPart.split("/").filter(Boolean);
  const params = Object.fromEntries(new URLSearchParams(query || ""));
  return { parts, params, path: "/" + parts.join("/") };
}

export function navigate(path) {
  if (!path.startsWith("#")) location.hash = `#${path}`;
  else location.hash = path;
}

export async function renderRoute() {
  const { parts, params, path } = parseHash();

  if (path !== "/admin/health") {
    stopHealthPolling();
  }

  if (PUBLIC_PATHS.has(path)) {
    updatePageSeo(path);
    trackPageView(path);
    await routes[path]?.(params);
    return;
  }

  const { state } = await import("./state.js");

  if (!state.isAuthenticated) {
    updatePageSeo("/login");
    trackPageView("/login");
    navigate("/login");
    return;
  }

  if (!state.hasApiKey && !JWT_ONLY_PATHS.has(path)) {
    navigate("/keys");
    return;
  }

  if (state.isAdminOnly && !path.startsWith("/admin")) {
    navigate("/admin/health");
    return;
  }

  if (path.startsWith("/admin") && !state.isAdmin) {
    navigate("/dashboard");
    return;
  }

  if (parts[0] === "admin" && parts[1] === "users" && parts[2]) {
    updatePageSeo("/admin/users");
    trackPageView(path);
    await routes["/admin/users/:id"]?.(parts[2], params);
    return;
  }

  const handler = routes[path];
  if (handler) {
    updatePageSeo(path);
    trackPageView(path);
    await handler(params);
    return;
  }

  navigate(state.hasApiKey ? "/dashboard" : "/keys");
}

export function initRouter() {
  window.addEventListener("hashchange", () => void renderRoute());
}
