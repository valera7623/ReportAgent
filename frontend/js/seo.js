/**
 * Dynamic SEO: title, meta, Open Graph, Twitter Cards, JSON-LD.
 * Works with hash-router SPA; crawlers that don't run JS still see index.html defaults.
 */

const SITE_NAME = "ReportAgent";

function siteOrigin() {
  if (typeof window !== "undefined" && window.REPORTAGENT_SITE_URL) {
    return String(window.REPORTAGENT_SITE_URL).replace(/\/$/, "");
  }
  return typeof window !== "undefined" ? window.location.origin : "";
}

function appBasePath() {
  const base = (typeof window !== "undefined" && window.REPORTAGENT_APP_BASE) || "/app";
  return base.replace(/\/$/, "");
}

export function absoluteUrl(path = "") {
  const origin = siteOrigin();
  const base = appBasePath();
  const hash = path.startsWith("#") ? path : path ? `#${path.replace(/^\//, "")}` : "";
  return `${origin}${base}/${hash}`.replace(/\/#/, "/#").replace(/([^:]\/)\/+/g, "$1");
}

export function ogImageUrl() {
  const custom = typeof window !== "undefined" && window.REPORTAGENT_OG_IMAGE;
  if (custom) return custom;
  return `${siteOrigin()}${appBasePath()}/og-image.png`;
}

function upsertMeta(attr, key, content) {
  if (content == null || content === "") return;
  let el = document.querySelector(`meta[${attr}="${key}"]`);
  if (!el) {
    el = document.createElement("meta");
    el.setAttribute(attr, key);
    document.head.appendChild(el);
  }
  el.setAttribute("content", content);
}

function upsertLink(rel, href, extra = {}) {
  if (!href) return;
  let el = document.querySelector(`link[rel="${rel}"]`);
  if (!el) {
    el = document.createElement("link");
    el.setAttribute("rel", rel);
    document.head.appendChild(el);
  }
  el.setAttribute("href", href);
  Object.entries(extra).forEach(([k, v]) => el.setAttribute(k, v));
}

function upsertJsonLd(id, data) {
  let el = document.getElementById(id);
  if (!data) {
    el?.remove();
    return;
  }
  if (!el) {
    el = document.createElement("script");
    el.type = "application/ld+json";
    el.id = id;
    document.head.appendChild(el);
  }
  el.textContent = JSON.stringify(data);
}

const DEFAULT_WEB_APP = {
  "@context": "https://schema.org",
  "@type": "WebApplication",
  name: SITE_NAME,
  applicationCategory: "BusinessApplication",
  operatingSystem: "Web",
  description:
    "Генерация отчётов из CSV, Excel и Google Sheets: PDF, Excel, PowerPoint, Notion и Google Slides с графиками и AI-анализом.",
  url: () => absoluteUrl("/dashboard"),
  offers: {
    "@type": "Offer",
    price: "0",
    priceCurrency: "USD",
    description: "Freemium — 5 отчётов в месяц",
  },
};

const PRICING_PRODUCT = {
  "@context": "https://schema.org",
  "@type": "Product",
  name: "ReportAgent — подписка",
  description: "Тарифные планы ReportAgent: Freemium, Premium и Enterprise.",
  brand: { "@type": "Brand", name: SITE_NAME },
  offers: [
    {
      "@type": "Offer",
      name: "Freemium",
      price: "0",
      priceCurrency: "USD",
      availability: "https://schema.org/InStock",
      description: "5 отчётов в месяц",
    },
    {
      "@type": "Offer",
      name: "Premium Monthly",
      price: "9.99",
      priceCurrency: "USD",
      availability: "https://schema.org/InStock",
      description: "100 отчётов в месяц",
    },
    {
      "@type": "Offer",
      name: "Premium Yearly",
      price: "99.00",
      priceCurrency: "USD",
      availability: "https://schema.org/InStock",
      description: "100 отчётов в месяц (годовая оплата)",
    },
    {
      "@type": "Offer",
      name: "Enterprise",
      price: "49.99",
      priceCurrency: "USD",
      availability: "https://schema.org/InStock",
      description: "1000 отчётов в месяц + Notion/Google Slides",
    },
  ],
};

/** Per-route SEO config (hash path without query). */
export const ROUTE_SEO = {
  "/dashboard": {
    title: "Дашборд — ReportAgent",
    description:
      "Панель управления ReportAgent: статистика отчётов, создание новых отчётов и мониторинг за последние 30 дней.",
    ogType: "website",
    jsonLd: DEFAULT_WEB_APP,
    noindex: false,
  },
  "/login": {
    title: "Вход — ReportAgent",
    description:
      "Войдите в ReportAgent по email и паролю или API-ключу. Генерация отчётов из таблиц с графиками и экспортом в PDF, Excel и PowerPoint.",
    ogType: "website",
    jsonLd: {
      "@context": "https://schema.org",
      "@type": "WebPage",
      name: "Вход — ReportAgent",
      description: "Страница входа в сервис ReportAgent.",
      url: () => absoluteUrl("/login"),
      isPartOf: { "@type": "WebSite", name: SITE_NAME, url: siteOrigin() },
    },
    noindex: false,
  },
  "/register": {
    title: "Регистрация — ReportAgent",
    description:
      "Создайте аккаунт ReportAgent: подтвердите email, получите API-ключ и начните генерировать отчёты из CSV и Google Sheets.",
    ogType: "website",
    jsonLd: {
      "@context": "https://schema.org",
      "@type": "WebPage",
      name: "Регистрация — ReportAgent",
      description: "Регистрация нового пользователя ReportAgent.",
      url: () => absoluteUrl("/register"),
      isPartOf: { "@type": "WebSite", name: SITE_NAME, url: siteOrigin() },
    },
    noindex: false,
  },
  "/pricing": {
    title: "Тарифы — ReportAgent",
    description:
      "Тарифы ReportAgent: Freemium, Premium и Enterprise. Оплата через Stripe Checkout. Гибкие лимиты отчётов в месяц.",
    ogType: "product",
    jsonLd: PRICING_PRODUCT,
    noindex: false,
  },
  "/pricing-yookassa": {
    title: "Тарифы (ЮKassa) — ReportAgent",
    description: "Оплата подписки ReportAgent через ЮKassa для пользователей из РФ.",
    ogType: "product",
    jsonLd: PRICING_PRODUCT,
    noindex: false,
  },
  "/reports": {
    title: "Отчёты — ReportAgent",
    description: "История сгенерированных отчётов: статус, формат, скачивание PDF, Excel и PowerPoint.",
    ogType: "website",
    noindex: true,
  },
  "/keys": {
    title: "API-ключи — ReportAgent",
    description: "Управление API-ключами ReportAgent: создание, ротация и отзыв ключей доступа.",
    ogType: "website",
    noindex: true,
  },
  "/webhooks": {
    title: "Вебхуки — ReportAgent",
    description: "Настройка webhook-уведомлений ReportAgent о готовности и ошибках генерации отчётов.",
    ogType: "website",
    noindex: true,
  },
  "/subscription": {
    title: "Подписка — ReportAgent",
    description: "Текущий тариф и использование лимита отчётов в ReportAgent.",
    ogType: "website",
    noindex: true,
  },
  "/preferences": {
    title: "Настройки — ReportAgent",
    description: "Персональные настройки ReportAgent: тема, формат отчётов, email и логотип компании.",
    ogType: "website",
    noindex: true,
  },
  "/verify": {
    title: "Подтверждение email — ReportAgent",
    description: "Подтверждение адреса электронной почты для аккаунта ReportAgent.",
    ogType: "website",
    noindex: true,
  },
  "/reset-password": {
    title: "Сброс пароля — ReportAgent",
    description: "Восстановление доступа к аккаунту ReportAgent.",
    ogType: "website",
    noindex: true,
  },
  "/reset-password/confirm": {
    title: "Новый пароль — ReportAgent",
    description: "Установка нового пароля для аккаунта ReportAgent.",
    ogType: "website",
    noindex: true,
  },
  "/success": {
    title: "Оплата успешна — ReportAgent",
    description: "Подписка ReportAgent успешно оформлена.",
    ogType: "website",
    noindex: true,
  },
  "/cancel": {
    title: "Оплата отменена — ReportAgent",
    description: "Оформление подписки ReportAgent отменено.",
    ogType: "website",
    noindex: true,
  },
  "/payment/success": {
    title: "Оплата успешна — ReportAgent",
    ogType: "website",
    noindex: true,
  },
  "/payment/cancel": {
    title: "Оплата отменена — ReportAgent",
    ogType: "website",
    noindex: true,
  },
};

function resolveJsonLd(schema) {
  if (!schema) return null;
  const copy = JSON.parse(JSON.stringify(schema, (_, v) => (typeof v === "function" ? v() : v)));
  if (copy.url && typeof copy.url === "object") delete copy.url;
  return copy;
}

/**
 * @param {string} path - Hash route path, e.g. "/pricing"
 * @param {object} [overrides] - Optional title/description overrides
 */
export function updatePageSeo(path, overrides = {}) {
  const normalized = path.split("?")[0] || "/dashboard";
  const isAdmin = normalized.startsWith("/admin");
  const config = ROUTE_SEO[normalized] || {
    title: isAdmin ? `Админ — ${SITE_NAME}` : `${SITE_NAME}`,
    description:
      "ReportAgent — автоматическая генерация отчётов из CSV, Excel и Google Sheets с графиками и AI.",
    ogType: "website",
    noindex: isAdmin,
  };

  const title = overrides.title || config.title;
  const description = overrides.description || config.description || "";
  const ogType = overrides.ogType || config.ogType || "website";
  const pageUrl = absoluteUrl(normalized);
  const image = ogImageUrl();
  const noindex = overrides.noindex ?? config.noindex ?? isAdmin;

  document.title = title;

  upsertMeta("name", "description", description);
  upsertMeta("name", "robots", noindex ? "noindex, nofollow" : "index, follow");

  upsertMeta("property", "og:title", title);
  upsertMeta("property", "og:description", description);
  upsertMeta("property", "og:url", pageUrl);
  upsertMeta("property", "og:type", ogType);
  upsertMeta("property", "og:site_name", SITE_NAME);
  upsertMeta("property", "og:image", image);
  upsertMeta("property", "og:image:width", "1200");
  upsertMeta("property", "og:image:height", "630");
  upsertMeta("property", "og:locale", "ru_RU");

  upsertMeta("name", "twitter:card", "summary_large_image");
  upsertMeta("name", "twitter:title", title);
  upsertMeta("name", "twitter:description", description);
  upsertMeta("name", "twitter:image", image);

  upsertLink("canonical", pageUrl);

  const jsonLd = resolveJsonLd(overrides.jsonLd ?? config.jsonLd);
  if (jsonLd && !jsonLd.url) {
    jsonLd.url = pageUrl;
  }
  upsertJsonLd("seo-json-ld", jsonLd);
}

export function initSeoPreconnect() {
  const apiBase = typeof window !== "undefined" && window.REPORTAGENT_API_BASE;
  if (!apiBase) return;
  try {
    const origin = new URL(apiBase, window.location.origin).origin;
    if (origin !== window.location.origin) {
      upsertLink("preconnect", origin);
      upsertLink("dns-prefetch", origin);
    }
  } catch {
    /* ignore invalid API base */
  }
}
