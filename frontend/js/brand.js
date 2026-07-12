/** Brand assets (logo + alt text). Paths relative to /app/ */

export const BRAND_NAME = "ReportAgent";

export const BRAND_LOGO_SIDEBAR = "assets/logo-sidebar.png";
export const BRAND_LOGO_FULL = "assets/logo.png";

export function brandLogoHtml({ variant = "sidebar", className = "" } = {}) {
  const src = variant === "full" ? BRAND_LOGO_FULL : BRAND_LOGO_SIDEBAR;
  const cls = ["brand-logo", variant === "full" ? "brand-logo--full" : "brand-logo--sidebar", className]
    .filter(Boolean)
    .join(" ");
  return `<img src="${src}" alt="${BRAND_NAME}" class="${cls}" width="220" height="40" decoding="async" />`;
}
