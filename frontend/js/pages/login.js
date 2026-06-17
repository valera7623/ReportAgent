import { authApi } from "../api/auth.js";
import { dashboardApi, adminApi } from "../api.js";
import { setApiKey, setJwt, clearJwt } from "../state.js";
import { navigate } from "../router.js";
import { toast } from "../ui.js";

export async function renderLogin(root, params = {}) {
  if (params.verified === "1") {
    toast("Email подтверждён. Войдите в аккаунт.", "success");
  } else if (params.verify_error) {
    toast(decodeURIComponent(params.verify_error), "error");
  }

  root.innerHTML = `
    <div class="login-page">
      <div class="login-card">
        <h1>ReportAgent</h1>
        <p class="seo-lead">Войдите в сервис генерации отчётов из CSV, Excel и Google Sheets с графиками и AI</p>
        <div class="tabs" style="display:flex;gap:.5rem;margin-bottom:1rem">
          <button type="button" class="btn btn-sm" id="tab-email" data-tab="email">Email</button>
          <button type="button" class="btn btn-outline btn-sm" id="tab-apikey" data-tab="apikey">API-ключ</button>
        </div>
        <div id="panel-email">
          <p>Вход по email и паролю</p>
          <form id="email-login-form">
            <div class="form-group">
              <label for="email">Email</label>
              <input id="email" type="email" required autocomplete="email" />
            </div>
            <div class="form-group">
              <label for="password">Пароль</label>
              <input id="password" type="password" required autocomplete="current-password" />
            </div>
            <button type="submit" class="btn" style="width:100%">Войти</button>
          </form>
          <p class="text-muted" style="margin-top:1rem;font-size:.85rem">
            <a href="#/register">Регистрация</a> ·
            <a href="#/reset-password">Забыли пароль?</a>
          </p>
        </div>
        <div id="panel-apikey" hidden>
          <p>Вход по API-ключу (админ или существующие пользователи)</p>
          <form id="apikey-login-form">
            <div class="form-group">
              <label for="api-key">API-ключ</label>
              <input id="api-key" type="password" placeholder="ra_... или ADMIN_API_KEY" autocomplete="off" required />
            </div>
            <button type="submit" class="btn" style="width:100%">Войти</button>
          </form>
        </div>
      </div>
    </div>`;

  const panelEmail = root.querySelector("#panel-email");
  const panelApiKey = root.querySelector("#panel-apikey");
  const tabEmail = root.querySelector("#tab-email");
  const tabApiKey = root.querySelector("#tab-apikey");

  function showTab(tab) {
    const isEmail = tab === "email";
    panelEmail.hidden = !isEmail;
    panelApiKey.hidden = isEmail;
    tabEmail.className = isEmail ? "btn btn-sm" : "btn btn-outline btn-sm";
    tabApiKey.className = isEmail ? "btn btn-outline btn-sm" : "btn btn-sm";
  }

  tabEmail.onclick = () => showTab("email");
  tabApiKey.onclick = () => showTab("apikey");

  root.querySelector("#email-login-form").onsubmit = async (e) => {
    e.preventDefault();
    const email = root.querySelector("#email").value.trim();
    const password = root.querySelector("#password").value;
    const btn = e.target.querySelector('button[type="submit"]');
    btn.disabled = true;
    btn.textContent = "Вход...";
    try {
      const res = await authApi.login({ email, password });
      clearJwt();
      setJwt(res.access_token, res.email);
      if (!res.is_verified) {
        toast("Подтвердите email перед генерацией API-ключа", "error");
        return;
      }
      toast("Вход выполнен. Создайте API-ключ.", "success");
      navigate("/keys");
    } catch (err) {
      toast(err.message || "Ошибка входа", "error");
    } finally {
      btn.disabled = false;
      btn.textContent = "Войти";
    }
  };

  root.querySelector("#apikey-login-form").onsubmit = async (e) => {
    e.preventDefault();
    const key = root.querySelector("#api-key").value.trim();
    if (!key) return;
    const btn = e.target.querySelector('button[type="submit"]');
    btn.disabled = true;
    btn.textContent = "Проверка...";
    try {
      localStorage.setItem("reportagent_api_key", key);
      clearJwt();

      let isUser = false;
      let isAdmin = false;
      const authOpts = { skipAuthRedirect: true };

      try {
        await adminApi.checkAdmin(authOpts);
        isAdmin = true;
      } catch {
        isAdmin = false;
      }

      try {
        await dashboardApi.stats(authOpts);
        isUser = true;
      } catch {
        isUser = false;
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
