import { API_KEY_STORAGE } from "../config.js";
import { mountShell } from "../layout.js";
import { loadingHtml, toast } from "../ui.js";
import { navigate } from "../router.js";
import { escapeHtml, formatUsdCents } from "../utils.js";
import { onError, paymentsApi } from "../api.js";
import { state } from "../state.js";

function getApiKey() {
  return localStorage.getItem(API_KEY_STORAGE);
}

async function startCheckout(priceId) {
  const apiKey = getApiKey();
  if (!apiKey) {
    toast("Войдите для оплаты", "error");
    navigate("/login");
    return;
  }

  const origin = window.location.origin;
  const data = await paymentsApi.createCheckout({
    price_id: priceId,
    success_url: `${origin}/success?session_id={CHECKOUT_SESSION_ID}`,
    cancel_url: `${origin}/cancel`,
  });

  if (!data?.url) {
    throw new Error("Stripe не вернул URL checkout");
  }

  sessionStorage.setItem("stripe_last_session_id", data.session_id);
  window.location.href = data.url;
}

export async function renderPricing(root) {
  if (!state.billingEnabled) {
    mountShell(
      root,
      "Тарифы",
      `<div class="page-header"><h2>Тарифы</h2></div>
       <div class="card"><div class="card-body">
         <p>Оплата Stripe временно отключена — включён <b>тестовый режим</b> без лимитов отчётов.</p>
         <button class="btn btn-outline" id="to-dash">На дашборд</button>
       </div></div>`,
      (el) => el.querySelector("#to-dash")?.addEventListener("click", () => navigate("/dashboard")),
    );
    return;
  }

  mountShell(root, "Тарифы", loadingHtml());

  let prices = [];
  try {
    const catalog = await paymentsApi.prices({ skipAuthRedirect: true });
    prices = catalog?.prices || [];
  } catch {
    prices = [];
  }

  const freemiumCard = `
    <div class="card">
      <div class="card-body">
        <h3>Freemium</h3>
        <p class="text-muted">Бесплатный старт</p>
        <div class="stat-value" style="margin:.75rem 0">$0</div>
        <p><b>5 отчётов / месяц</b></p>
        <button class="btn btn-outline" disabled>Включено</button>
      </div>
    </div>`;

  const paidCards =
    prices.length > 0
      ? prices
          .map(
            (p) => `
        <div class="card">
          <div class="card-body">
            <h3>${escapeHtml(p.name)}</h3>
            <p class="text-muted">${escapeHtml(p.interval ? `/${p.interval}` : "one-time")}</p>
            <div class="stat-value" style="margin:.75rem 0">${formatUsdCents(p.amount)}</div>
            <p><b>${p.id.includes("PAYG") || p.name.toLowerCase().includes("pay") ? "1000" : "100"} отчётов / месяц</b></p>
            <button class="btn" data-stripe-price="${escapeHtml(p.id)}">Купить через Stripe</button>
          </div>
        </div>`,
          )
          .join("")
      : `
        <div class="card"><div class="card-body">
          <p class="text-muted">Настройте STRIPE_PRICE_ID_* в .env для отображения тарифов.</p>
          <button class="btn btn-outline" disabled>Stripe не настроен</button>
        </div></div>`;

  const yookassaNote = `
    <p class="text-muted" style="margin-top:1.5rem">
      Альтернатива для РФ: <a href="#/pricing-yookassa">оплата через ЮKassa</a>
    </p>`;

  mountShell(
    root,
    "Тарифы",
    `
    <div class="page-header"><h2>Тарифы</h2><p>Оплата подписки через Stripe Checkout</p></div>
    <div class="grid-4">${freemiumCard}${paidCards}</div>
    ${yookassaNote}`,
    (el) => {
      el.querySelectorAll("[data-stripe-price]").forEach((btn) => {
        btn.onclick = async () => {
          btn.disabled = true;
          const label = btn.textContent;
          btn.textContent = "Перенаправление...";
          try {
            await startCheckout(btn.dataset.stripePrice);
          } catch (err) {
            onError(err);
            btn.disabled = false;
            btn.textContent = label;
          }
        };
      });
    },
  );
}
