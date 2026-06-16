import { preferencesApi, onError } from "../api.js";
import { mountShell } from "../layout.js";
import { setTheme } from "../state.js";
import { loadingHtml, toast } from "../ui.js";
import { OUTPUT_FORMATS } from "../config.js";

export async function renderPreferences(root) {
  mountShell(root, "Настройки", loadingHtml());
  try {
    const prefs = await preferencesApi.get();
    mountShell(
      root,
      "Настройки",
      `
      <div class="page-header"><h2>Настройки</h2><p>Персональные предпочтения</p></div>
      <div class="card" style="max-width:480px">
        <div class="card-body">
          <form id="prefs-form">
            <div class="form-group"><label>Тип графика</label>
              <select name="preferred_chart_type">
                <option value="bar" ${prefs.preferred_chart_type === "bar" ? "selected" : ""}>Столбчатый</option>
                <option value="line" ${prefs.preferred_chart_type === "line" ? "selected" : ""}>Линейный</option>
                <option value="pie" ${prefs.preferred_chart_type === "pie" ? "selected" : ""}>Круговой</option>
              </select>
            </div>
            <div class="form-group"><label>Тема</label>
              <select name="theme">
                <option value="light" ${prefs.theme === "light" ? "selected" : ""}>Светлая</option>
                <option value="dark" ${prefs.theme === "dark" ? "selected" : ""}>Тёмная</option>
              </select>
            </div>
            <div class="form-group"><label>Email по умолчанию</label>
              <input name="default_email" type="email" value="${prefs.default_email || ""}" />
            </div>
            <div class="form-group"><label>Формат по умолчанию</label>
              <select name="default_output_format">
                ${OUTPUT_FORMATS.map((f) => `<option value="${f.value}" ${prefs.default_output_format === f.value ? "selected" : ""}>${f.label}</option>`).join("")}
              </select>
            </div>
            <div class="form-group"><label>Часовой пояс</label>
              <input name="timezone" value="${prefs.timezone || "UTC"}" />
            </div>
            <button type="submit" class="btn">Сохранить</button>
          </form>
        </div>
      </div>`,
      (el) => {
        el.querySelector("#prefs-form").onsubmit = async (e) => {
          e.preventDefault();
          const fd = new FormData(e.target);
          const body = Object.fromEntries(fd.entries());
          body.default_email = body.default_email || null;
          try {
            await preferencesApi.update(body);
            setTheme(body.theme);
            toast("Сохранено", "success");
          } catch (err) {
            onError(err);
          }
        };
      },
    );
  } catch (err) {
    onError(err);
  }
}
