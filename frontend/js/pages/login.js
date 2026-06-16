import { dashboardApi, adminApi, onError } from "../api.js";
import { setApiKey } from "../state.js";
import { navigate } from "../router.js";
import { toast } from "../ui.js";

export async function renderLogin(root) {
  root.innerHTML = `
    <div class="login-page">
      <div class="login-card">
        <h1>🛡️ ReportAgent</h1>
        <p>Введите API-ключ для доступа</p>
        <form id="login-form">
          <div class="form-group">
            <label for="api-key">API-ключ</label>
            <input id="api-key" type="password" placeholder="ra_..." autocomplete="off" required />
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
      await dashboardApi.stats();
      let isAdmin = false;
      try {
        await adminApi.checkAdmin();
        isAdmin = true;
      } catch {
        isAdmin = false;
      }
      setApiKey(key, isAdmin);
      toast(isAdmin ? "Вход (админ)" : "Вход выполнен", "success");
      navigate("/dashboard");
    } catch (err) {
      localStorage.removeItem("reportagent_api_key");
      onError(err);
    } finally {
      btn.disabled = false;
      btn.textContent = "Войти";
    }
  };
}
