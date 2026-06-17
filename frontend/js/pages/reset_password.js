import { authApi } from "../api/auth.js";
import { navigate } from "../router.js";
import { toast } from "../ui.js";

export async function renderResetPassword(root, params = {}) {
  const token = params.token;
  const isConfirm = Boolean(token);

  if (isConfirm) {
    root.innerHTML = `
      <div class="login-page">
        <div class="login-card">
          <h1>🛡️ ReportAgent</h1>
          <p>Новый пароль</p>
          <form id="reset-confirm-form">
            <div class="form-group">
              <label for="new-password">Новый пароль (мин. 8 символов)</label>
              <input id="new-password" type="password" minlength="8" required autocomplete="new-password" />
            </div>
            <button type="submit" class="btn" style="width:100%">Сохранить пароль</button>
          </form>
        </div>
      </div>`;

    root.querySelector("#reset-confirm-form").onsubmit = async (e) => {
      e.preventDefault();
      const new_password = root.querySelector("#new-password").value;
      const btn = e.target.querySelector('button[type="submit"]');
      btn.disabled = true;
      try {
        await authApi.resetPassword({ token, new_password });
        toast("Пароль обновлён", "success");
        navigate("/login");
      } catch (err) {
        toast(err.message || "Ошибка сброса", "error");
      } finally {
        btn.disabled = false;
      }
    };
    return;
  }

  root.innerHTML = `
    <div class="login-page">
      <div class="login-card">
        <h1>🛡️ ReportAgent</h1>
        <p>Сброс пароля</p>
        <form id="reset-request-form">
          <div class="form-group">
            <label for="email">Email</label>
            <input id="email" type="email" required autocomplete="email" />
          </div>
          <button type="submit" class="btn" style="width:100%">Отправить ссылку</button>
        </form>
        <p class="text-muted" style="margin-top:1rem;font-size:.85rem">
          <a href="#/login">Вернуться ко входу</a>
        </p>
      </div>
    </div>`;

  root.querySelector("#reset-request-form").onsubmit = async (e) => {
    e.preventDefault();
    const email = root.querySelector("#email").value.trim();
    const btn = e.target.querySelector('button[type="submit"]');
    btn.disabled = true;
    try {
      await authApi.requestResetPassword({ email });
      toast("Если email зарегистрирован, ссылка отправлена", "success");
      navigate("/login");
    } catch (err) {
      toast(err.message || "Ошибка", "error");
    } finally {
      btn.disabled = false;
    }
  };
}
