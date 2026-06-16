import { mountShell } from "../layout.js";
import { navigate } from "../router.js";

export async function renderSuccess(root, params = {}) {
  const sessionId =
    params?.session_id || sessionStorage.getItem("stripe_last_session_id") || "";

  mountShell(
    root,
    "Спасибо!",
    `<div class="card"><div class="card-body">
      <h3>✅ Оплата прошла успешно</h3>
      <p>Подписка активируется в течение минуты после подтверждения Stripe webhook.</p>
      ${sessionId ? `<p class="mono text-muted">session: ${sessionId}</p>` : ""}
      <div style="display:flex;gap:.75rem;margin-top:1rem">
        <button class="btn" id="to-dashboard">К дашборду</button>
        <button class="btn btn-outline" id="to-sub">Моя подписка</button>
      </div>
    </div></div>`,
    (el) => {
      el.querySelector("#to-dashboard")?.addEventListener("click", () => navigate("/dashboard"));
      el.querySelector("#to-sub")?.addEventListener("click", () => navigate("/subscription"));
    },
  );
}
