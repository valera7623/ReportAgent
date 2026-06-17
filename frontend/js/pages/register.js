import { authApi } from "../api/auth.js";
import { navigate } from "../router.js";
import { toast } from "../ui.js";

export async function renderRegister(root) {
  root.innerHTML = `
    <div class="login-page">
      <div class="login-card">
        <h1>🛡️ ReportAgent</h1>
        <p>Регистрация</p>
        <form id="register-form">
          <div class="form-group">
            <label for="email">Email</label>
            <input id="email" type="email" required autocomplete="email" />
          </div>
          <div class="form-group">
            <label for="password">Пароль (мин. 8 символов)</label>
            <input id="password" type="password" minlength="8" required autocomplete="new-password" />
          </div>
          <div class="form-group">
            <label for="password-confirm">Подтверждение пароля</label>
            <input id="password-confirm" type="password" minlength="8" required autocomplete="new-password" />
          </div>
          <button type="submit" class="btn" style="width:100%">Зарегистрироваться</button>
        </form>
        <p class="text-muted" style="margin-top:1rem;font-size:.9rem">
          Уже есть аккаунт? <a href="#/login">Войти</a>
        </p>
      </div>
    </div>`;

  root.querySelector("#register-form").onsubmit = async (e) => {
    e.preventDefault();
    const email = root.querySelector("#email").value.trim();
    const password = root.querySelector("#password").value;
    const password_confirm = root.querySelector("#password-confirm").value;
    const btn = root.querySelector('button[type="submit"]');
    btn.disabled = true;
    btn.textContent = "Регистрация...";
    try {
      await authApi.register({ email, password, password_confirm });
      toast("Проверьте почту для подтверждения email", "success");
      navigate("/login");
    } catch (err) {
      toast(err.message || "Ошибка регистрации", "error");
    } finally {
      btn.disabled = false;
      btn.textContent = "Зарегистрироваться";
    }
  };
}
