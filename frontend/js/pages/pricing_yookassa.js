import { API_BASE, API_KEY_STORAGE } from "../config.js";
import { mountShell } from "../layout.js";
import { loadingHtml, toast } from "../ui.js";
import { navigate } from "../router.js";
import { escapeHtml } from "../utils.js";

const PLANS = [
  { key: "freemium", title: "Freemium", subtitle: "Бесплатно", reports: "5 отчётов / месяц", priceLabel: "0 ₽", action: null },
  { key: "premium_monthly", title: "Premium (Monthly)", subtitle: "Подписка каждый месяц", reports: "100 отчётов / месяц", priceLabel: "19.90 ₽", action: "premium_monthly" },
  { key: "premium_yearly", title: "Premium (Yearly)", subtitle: "Подписка на год", reports: "100 отчётов / месяц", priceLabel: "199.00 ₽ / год", action: "premium_yearly" },
  { key: "enterprise", title: "Enterprise", subtitle: "Максимальные лимиты", reports: "1000 отчётов / месяц (все форматы)", priceLabel: "99.90 ₽", action: "enterprise" },
];

function getApiKey() {
  return localStorage.getItem(API_KEY_STORAGE);
}

async function createAndRedirect(plan_type) {
  const apiKey = getApiKey();
  if (!apiKey) {
    toast("Войдите для оплаты", "error");
    navigate("/login");
    return;
  }

  const res = await fetch(`${API_BASE}/api/payments/yookassa/create`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-API-Key": apiKey },
    body: JSON.stringify({ plan_type }),
  });

  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { detail: text };
  }

  if (!res.ok) {
    toast(data?.detail || "Не удалось создать платёж", "error");
    throw new Error(data?.detail || "Create payment failed");
  }

  sessionStorage.setItem("yookassa_last_payment_id", data.payment_id);
  window.location.href = data.confirmation_url;
}

export async function renderPricingYookassa(root) {
  mountShell(root, "Тарифы (ЮKassa)", loadingHtml());

  const html = `
    <div class="page-header">
      <h1>Тарифы — ЮKassa</h1>
      <p class="seo-lead">Оплата подписки ReportAgent картами РФ через ЮKassa</p>
      <p><a href="#/pricing">← Stripe (основной)</a></p>
    </div>
    <div class="grid-4">
      ${PLANS.map(
        (p) => `
        <div class="card"><div class="card-body">
          <h3>${escapeHtml(p.title)}</h3>
          <p class="text-muted">${escapeHtml(p.subtitle)}</p>
          <div class="stat-value" style="margin:.75rem 0">${escapeHtml(p.priceLabel)}</div>
          <p><b>${escapeHtml(p.reports)}</b></p>
          <div style="margin-top:1rem">
            ${p.action ? `<button class="btn" data-buy="${escapeHtml(p.action)}">Оплатить через ЮKassa</button>` : `<button class="btn btn-outline" disabled>Бесплатно</button>`}
          </div>
        </div></div>`,
      ).join("")}
    </div>`;

  mountShell(root, "Тарифы (ЮKassa)", html, (el) => {
    el.querySelectorAll("[data-buy]").forEach((b) => {
      b.onclick = async () => {
        b.disabled = true;
        const original = b.textContent;
        b.textContent = "Создание платежа...";
        try {
          await createAndRedirect(b.dataset.buy);
        } catch {
          b.disabled = false;
          b.textContent = original;
        }
      };
    });
  });
}
