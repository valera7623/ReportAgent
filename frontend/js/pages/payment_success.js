import { API_BASE, API_KEY_STORAGE } from "../config.js";
import { mountShell } from "../layout.js";
import { loadingHtml, toast } from "../ui.js";
import { navigate } from "../router.js";
import { escapeHtml } from "../utils.js";

function getApiKey() {
  return localStorage.getItem(API_KEY_STORAGE);
}

function getPaymentId(params) {
  return params?.payment_id || params?.id || params?.paymentId || "";
}

async function fetchStatus(payment_id) {
  const apiKey = getApiKey();
  const res = await fetch(`${API_BASE}/api/payments/yookassa/status/${payment_id}`, {
    method: "GET",
    headers: apiKey ? { "X-API-Key": apiKey } : {},
  });
  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { detail: text };
  }
  if (!res.ok) throw new Error(data?.detail || `HTTP ${res.status}`);
  return data;
}

export async function renderPaymentSuccess(root, params = {}) {
  mountShell(root, "Оплата", loadingHtml("Проверяем статус платежа..."));

  const payment_id =
    getPaymentId(params) || sessionStorage.getItem("yookassa_last_payment_id") || "";
  if (!payment_id) {
    toast("Не найден payment_id после оплаты", "error");
    mountShell(root, "Оплата", `<p class="text-muted">Не удалось определить идентификатор платежа.</p>`);
    return;
  }

  try {
    const statusData = await fetchStatus(payment_id);
    const status = statusData?.status;

    if (status === "canceled") {
      navigate(`/payment/cancel?payment_id=${encodeURIComponent(payment_id)}`);
      return;
    }

    if (status !== "succeeded") {
      mountShell(
        root,
        "Оплата",
        `<div class="card"><div class="card-body">
          <h3>Оплата в процессе</h3>
          <p class="text-muted">Статус: ${escapeHtml(status || "pending")}</p>
          <p>Премиум будет доступен сразу после подтверждения вебхуком.</p>
          <p class="mono" style="margin-top:1rem">payment_id: ${escapeHtml(payment_id)}</p>
        </div></div>`,
      );
      return;
    }

    mountShell(
      root,
      "Оплата прошла успешно",
      `<div class="card"><div class="card-body">
        <h3>✅ Подписка активирована</h3>
        <p>Лимиты обновлены. Можете продолжать работу.</p>
        <div style="display:flex;gap:.75rem;flex-wrap:wrap;margin-top:1rem">
          <button class="btn" id="to-dashboard">К дашборду</button>
          <button class="btn btn-outline" id="to-pricing">Управлять тарифом</button>
        </div>
        <p class="mono" style="margin-top:1rem">payment_id: ${escapeHtml(payment_id)}</p>
      </div></div>`,
      (el) => {
        el.querySelector("#to-dashboard")?.addEventListener("click", () => navigate("/dashboard"));
        el.querySelector("#to-pricing")?.addEventListener("click", () => navigate("/pricing"));
      },
    );
  } catch (err) {
    toast(err.message || "Ошибка проверки платежа", "error");
    mountShell(root, "Оплата", `<p class="text-muted">Ошибка проверки статуса платежа. Попробуйте позже.</p>`);
  }
}

