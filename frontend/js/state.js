import { API_KEY_STORAGE, JWT_STORAGE } from "./config.js";

const listeners = new Set();

export const state = {
  apiKey: localStorage.getItem(API_KEY_STORAGE),
  jwt: localStorage.getItem(JWT_STORAGE),
  userEmail: localStorage.getItem("reportagent_user_email"),
  isAdmin: false,
  isAdminOnly: false,
  isAuthenticated: !!(
    localStorage.getItem(API_KEY_STORAGE) || localStorage.getItem(JWT_STORAGE)
  ),
  hasApiKey: !!localStorage.getItem(API_KEY_STORAGE),
  billingEnabled: true,
  theme: localStorage.getItem("reportagent_theme") || "light",
  sidebarOpen: false,
};

export function subscribe(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function notify() {
  listeners.forEach((fn) => fn(state));
}

export function setApiKey(key, isAdmin = false, isAdminOnly = false) {
  localStorage.setItem(API_KEY_STORAGE, key);
  state.apiKey = key;
  state.hasApiKey = true;
  state.isAdmin = isAdmin;
  state.isAdminOnly = isAdminOnly;
  state.isAuthenticated = true;
  notify();
}

export function setJwt(token, email = null) {
  localStorage.setItem(JWT_STORAGE, token);
  state.jwt = token;
  state.isAuthenticated = true;
  if (email) {
    localStorage.setItem("reportagent_user_email", email);
    state.userEmail = email;
  }
  notify();
}

export function clearJwt() {
  localStorage.removeItem(JWT_STORAGE);
  localStorage.removeItem("reportagent_user_email");
  state.jwt = null;
  state.userEmail = null;
  notify();
}

export function setIsAdmin(v) {
  state.isAdmin = v;
  notify();
}

export function setBillingEnabled(v) {
  state.billingEnabled = !!v;
  notify();
}

export function logout() {
  localStorage.removeItem(API_KEY_STORAGE);
  localStorage.removeItem(JWT_STORAGE);
  localStorage.removeItem("reportagent_user_email");
  state.apiKey = null;
  state.jwt = null;
  state.userEmail = null;
  state.hasApiKey = false;
  state.isAdmin = false;
  state.isAdminOnly = false;
  state.isAuthenticated = false;
  notify();
}

export function setTheme(theme) {
  localStorage.setItem("reportagent_theme", theme);
  state.theme = theme;
  document.documentElement.dataset.theme = theme;
  notify();
}

export function toggleTheme() {
  setTheme(state.theme === "dark" ? "light" : "dark");
}

export function toggleSidebar(open) {
  state.sidebarOpen = open ?? !state.sidebarOpen;
  notify();
}

export function initState() {
  document.documentElement.dataset.theme = state.theme;
}
