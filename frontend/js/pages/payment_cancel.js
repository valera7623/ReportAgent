import { mountShell } from "../layout.js";
import { loadingHtml, toast } from "../ui.js";
import { navigate } from "../router.js";
import { escapeHtml } from "../utils.js";

export async function renderPaymentCancel(root, params = {}) {
  mountShell(root, "Оплата отменена", loadingHtml("Подготавливаем страницу отмены..."));

  const payment_id = params?.payment_id || params?.id || params?.paymentId || "";
  if (!payment_id) {
    toast("payment_id не найден", "error");
  }

  mountShell(
    root,
    "Оплата отменена",
    `<div class="card"><div class="card-body">
      <h3>❌ Оплата отменена</h3>
      <p class="text-muted">Средства не списаны или платеж был отменён.</p>
      <div style="display:flex;gap:.75rem;flex-wrap:wrap;margin-top:1rem">
        <button class="btn" id="to-pricing">Повторить оплату</button>
        <button class="btn btn-outline" id="to-dashboard">На дашборд</button>
      </div>
      ${payment_id ? `<p class="mono" style="margin-top:1rem">payment_id: ${escapeHtml(payment_id)}</p>` : ""}
    </div></div>`,
    (el) => {
      el.querySelector("#to-pricing")?.addEventListener("click", () => navigate("/pricing"));
      el.querySelector("#to-dashboard")?.addEventListener("click", () => navigate("/dashboard"));
    },
  );
}

