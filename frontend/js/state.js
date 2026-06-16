import { API_KEY_STORAGE, THEME_STORAGE } from "./config.js";

const listeners = new Set();

export const state = {
  apiKey: localStorage.getItem(API_KEY_STORAGE),
  isAdmin: false,
  isAdminOnly: false,
  isAuthenticated: !!localStorage.getItem(API_KEY_STORAGE),
  theme: localStorage.getItem(THEME_STORAGE) || "light",
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
  state.isAdmin = isAdmin;
  state.isAdminOnly = isAdminOnly;
  state.isAuthenticated = true;
  notify();
}

export function setIsAdmin(v) {
  state.isAdmin = v;
  notify();
}

export function logout() {
  localStorage.removeItem(API_KEY_STORAGE);
  state.apiKey = null;
  state.isAdmin = false;
  state.isAdminOnly = false;
  state.isAuthenticated = false;
  notify();
}

export function setTheme(theme) {
  localStorage.setItem(THEME_STORAGE, theme);
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
