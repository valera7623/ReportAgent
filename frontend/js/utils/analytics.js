/**
 * Google Analytics 4 + Yandex Metrika with SPA page_view on hash navigation.
 *
 * Configure via index.html or window globals before app.js:
 *   window.REPORTAGENT_GA4_ID = 'G-XXXXXXXX';
 *   window.REPORTAGENT_YM_ID = '12345678';
 */

let initialized = false;

function ga4Id() {
  return (typeof window !== "undefined" && window.REPORTAGENT_GA4_ID) || "";
}

function ymId() {
  return (typeof window !== "undefined" && window.REPORTAGENT_YM_ID) || "";
}

function loadScript(src, id) {
  return new Promise((resolve, reject) => {
    if (document.getElementById(id)) {
      resolve();
      return;
    }
    const s = document.createElement("script");
    s.id = id;
    s.async = true;
    s.src = src;
    s.onload = () => resolve();
    s.onerror = () => reject(new Error(`Failed to load ${src}`));
    document.head.appendChild(s);
  });
}

function initGa4() {
  const id = ga4Id();
  if (!id) return;

  window.dataLayer = window.dataLayer || [];
  window.gtag = function gtag() {
    window.dataLayer.push(arguments);
  };
  window.gtag("js", new Date());
  window.gtag("config", id, { send_page_view: false });

  loadScript(`https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(id)}`, "ga4-script").catch(
    () => {},
  );
}

function initYandex() {
  const id = ymId();
  if (!id) return;

  window.ym =
    window.ym ||
    function ymStub() {
      (window.ym.a = window.ym.a || []).push(arguments);
    };
  window.ym.l = Date.now();

  loadScript("https://mc.yandex.ru/metrika/tag.js", "ym-script")
    .then(() => {
      window.ym(Number(id), "init", {
        clickmap: true,
        trackLinks: true,
        accurateTrackBounce: true,
        webvisor: false,
      });
    })
    .catch(() => {});
}

export function initAnalytics() {
  if (initialized || typeof window === "undefined") return;
  initialized = true;
  initGa4();
  initYandex();
}

export function trackPageView(path) {
  const pagePath = path || `${window.location.pathname}${window.location.hash || ""}`;
  const pageLocation = window.location.href;
  const pageTitle = document.title;

  const ga = ga4Id();
  if (ga && typeof window.gtag === "function") {
    window.gtag("event", "page_view", {
      page_title: pageTitle,
      page_location: pageLocation,
      page_path: pagePath,
    });
  }

  const ym = ymId();
  if (ym && typeof window.ym === "function") {
    try {
      window.ym(Number(ym), "hit", pageLocation, { title: pageTitle });
    } catch {
      /* Metrika not ready yet */
    }
  }
}
