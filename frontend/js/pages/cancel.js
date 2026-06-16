import { mountShell } from "../layout.js";
import { navigate } from "../router.js";

export async function renderCancel(root) {
  mountShell(
    root,
    "Оплата отменена",
    `<div class="card"><div class="card-body">
      <h3>Оплата не завершена</h3>
      <p class="text-muted">Вы можете вернуться к тарифам и попробовать снова.</p>
      <div style="display:flex;gap:.75rem;margin-top:1rem">
        <button class="btn" id="to-pricing">К тарифам</button>
        <button class="btn btn-outline" id="to-dashboard">На дашборд</button>
      </div>
    </div></div>`,
    (el) => {
      el.querySelector("#to-pricing")?.addEventListener("click", () => navigate("/pricing"));
      el.querySelector("#to-dashboard")?.addEventListener("click", () => navigate("/dashboard"));
    },
  );
}
