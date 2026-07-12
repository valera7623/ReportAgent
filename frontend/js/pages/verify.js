import { authApi } from "../api/auth.js";
import { navigate } from "../router.js";
import { toast } from "../ui.js";
import { brandLogoHtml } from "../brand.js";

export async function renderVerify(root, params = {}) {
  const email = params.email || "";
  const token = params.token || "";

  root.innerHTML = `
    <div class="login-page">
      <div class="login-card">
        <div class="login-brand">${brandLogoHtml({ variant: "full", className: "brand-logo--auth" })}</div>
        <p id="verify-status">Подтверждение email…</p>
      </div>
    </div>`;

  const statusEl = root.querySelector("#verify-status");

  if (!email || !token) {
    statusEl.textContent = "Неверная ссылка подтверждения.";
    return;
  }

  try {
    await authApi.verify({ email, token });
    statusEl.textContent = "Email подтверждён! Перенаправление на вход…";
    toast("Email подтверждён", "success");
    setTimeout(() => navigate("/login"), 1500);
  } catch (err) {
    statusEl.textContent = err.message || "Ошибка подтверждения";
    toast(err.message || "Ошибка подтверждения", "error");
  }
}
