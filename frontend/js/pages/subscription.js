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
    const provider = (sub.payment_provider || "").toLowerCase();
    const providerLabel =
      provider === "yookassa" ? "ЮKassa" : provider === "stripe" ? "Stripe" : escapeHtml(provider || "—");

    const billingNote = sub.billing_note
      ? `<p class="text-muted" style="margin-top:.75rem">${escapeHtml(sub.billing_note)}</p>`
      : provider === "yookassa"
        ? `<p class="text-muted" style="margin-top:.75rem">ЮKassa — разовая оплата на период (не автопродление). Продлите вручную до истечения срока.</p>`
        : "";

    const canCancelStripe = Boolean(sub.stripe_subscription_id && sub.is_active);
    const canCancelYookassa = provider === "yookassa" && sub.is_active && !sub.stripe_subscription_id;
    const cancelBtn =
      canCancelStripe || canCancelYookassa
        ? `<button class="btn btn-outline btn-danger" id="cancel-sub">Отменить доступ</button>`
        : "";

    const renewBtn =
      provider === "yookassa"
        ? `<button class="btn" id="renew-yookassa">Продлить (ЮKassa)</button>`
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
          <p><b>Провайдер:</b> ${providerLabel}</p>
          <p><b>Отчёты:</b> ${sub.reports_used} / ${sub.reports_limit} (осталось ${sub.reports_remaining})</p>
          ${periodEnd}
          ${billingNote}
          <div style="display:flex;gap:.75rem;flex-wrap:wrap;margin-top:1.25rem">
            <button class="btn" id="to-pricing">Сменить тариф</button>
            ${renewBtn}
            ${cancelBtn}
          </div>
        </div>
      </div>`,
      (el) => {
        el.querySelector("#to-pricing")?.addEventListener("click", () => navigate("/pricing"));
        el.querySelector("#renew-yookassa")?.addEventListener("click", () => navigate("/pricing-yookassa"));
        el.querySelector("#cancel-sub")?.addEventListener("click", async () => {
          const msg = canCancelYookassa
            ? "Завершить оплаченный период ЮKassa сейчас? Доступ сразу станет Freemium."
            : "Отменить подписку? Доступ сохранится до конца оплаченного периода.";
          if (!(await confirmDialog("Отменить подписку?", msg))) {
            return;
          }
          try {
            const res = await paymentsApi.cancelSubscription();
            toast(
              `Подписка отменена${res.effective_date ? ` (до ${formatDate(res.effective_date)})` : ""}`,
              "success",
            );
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
