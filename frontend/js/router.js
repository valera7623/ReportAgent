const routes = {};

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

  if (path === "/login") {
    await routes["/login"]?.(params);
    return;
  }

  const { state } = await import("./state.js");
  if (!state.isAuthenticated) {
    navigate("/login");
    return;
  }

  if (path.startsWith("/admin") && !state.isAdmin) {
    navigate("/dashboard");
    return;
  }

  if (parts[0] === "admin" && parts[1] === "users" && parts[2]) {
    await routes["/admin/users/:id"]?.(parts[2], params);
    return;
  }

  const handler = routes[path];
  if (handler) {
    await handler(params);
    return;
  }

  navigate("/dashboard");
}

export function initRouter() {
  window.addEventListener("hashchange", () => void renderRoute());
}
