import { dashboardApi, adminApi } from "../api.js";
import { setApiKey } from "../state.js";
import { navigate } from "../router.js";
import { toast } from "../ui.js";

export async function renderLogin(root) {
  root.innerHTML = `
    <div class="login-page">
      <div class="login-card">
        <h1>🛡️ ReportAgent</h1>
        <p>Введите API-ключ для доступа</p>
        <p class="text-muted" style="font-size:.85rem;margin-bottom:1rem">
          Пользовательский ключ: <code>ra_...</code><br>
          Админский ключ: <code>ADMIN_API_KEY</code> (только админ-панель)
        </p>
        <form id="login-form">
          <div class="form-group">
            <label for="api-key">API-ключ</label>
            <input id="api-key" type="password" placeholder="ra_... или ADMIN_API_KEY" autocomplete="off" required />
          </div>
          <button type="submit" class="btn" style="width:100%">Войти</button>
        </form>
      </div>
    </div>`;

  root.querySelector("#login-form").onsubmit = async (e) => {
    e.preventDefault();
    const key = root.querySelector("#api-key").value.trim();
    if (!key) return;
    const btn = root.querySelector('button[type="submit"]');
    btn.disabled = true;
    btn.textContent = "Проверка...";
    try {
      localStorage.setItem("reportagent_api_key", key);

      let isUser = false;
      let isAdmin = false;

      try {
        await dashboardApi.stats({ skipAuthRedirect: true });
        isUser = true;
      } catch {
        isUser = false;
      }

      try {
        await adminApi.checkAdmin({ skipAuthRedirect: true });
        isAdmin = true;
      } catch {
        isAdmin = false;
      }

      if (!isUser && !isAdmin) {
        localStorage.removeItem("reportagent_api_key");
        toast("Неверный API-ключ", "error");
        return;
      }

      const isAdminOnly = isAdmin && !isUser;
      setApiKey(key, isAdmin, isAdminOnly);
      toast(
        isAdminOnly ? "Вход (только админ)" : isAdmin ? "Вход (админ + пользователь)" : "Вход выполнен",
        "success",
      );
      navigate(isUser ? "/dashboard" : "/admin/health");
    } catch (err) {
      localStorage.removeItem("reportagent_api_key");
      toast(err.message || "Ошибка входа", "error");
    } finally {
      btn.disabled = false;
      btn.textContent = "Войти";
    }
  };
}
