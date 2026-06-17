import { paymentsApi, onError } from "../api.js";
import { mountShell } from "../layout.js";
import { confirmDialog, loadingHtml, toast } from "../ui.js";
import { escapeHtml, formatDate, planLabel } from "../utils.js";
import { navigate } from "../router.js";

export async function renderSubscription(root) {
  mountShell(root, "Подписка", loadingHtml());

  try {
    const sub = await paymentsApi.subscription();
    const periodEnd = sub.current_period_end
      ? `<p><b>Действует до:</b> ${formatDate(sub.current_period_end)}</p>`
      : "";

    const cancelBtn =
      sub.stripe_subscription_id && sub.is_active
        ? `<button class="btn btn-outline btn-danger" id="cancel-sub">Отменить подписку</button>`
        : "";

    mountShell(
      root,
      "Подписка",
      `
      <div class="page-header"><h1>Подписка</h1><p class="seo-lead">Текущий тариф и использование лимита отчётов</p></div>
      <div class="card" style="max-width:520px">
        <div class="card-body">
          <p><b>Тариф:</b> ${escapeHtml(planLabel(sub.plan_type))}</p>
          <p><b>Статус:</b> ${escapeHtml(sub.status)}</p>
          <p><b>Отчёты:</b> ${sub.reports_used} / ${sub.reports_limit} (осталось ${sub.reports_remaining})</p>
          ${periodEnd}
          <div style="display:flex;gap:.75rem;flex-wrap:wrap;margin-top:1.25rem">
            <button class="btn" id="to-pricing">Сменить тариф</button>
            ${cancelBtn}
          </div>
        </div>
      </div>`,
      (el) => {
        el.querySelector("#to-pricing")?.addEventListener("click", () => navigate("/pricing"));
        el.querySelector("#cancel-sub")?.addEventListener("click", async () => {
          if (!(await confirmDialog("Отменить подписку?", "Доступ сохранится до конца оплаченного периода."))) {
            return;
          }
          try {
            const res = await paymentsApi.cancelSubscription();
            toast(`Подписка отменена${res.effective_date ? ` (до ${formatDate(res.effective_date)})` : ""}`, "success");
            renderSubscription(root);
          } catch (err) {
            onError(err);
          }
        });
      },
    );
  } catch (err) {
    onError(err);
    mountShell(root, "Подписка", `<p class="text-muted">Не удалось загрузить данные подписки.</p>`);
  }
}
