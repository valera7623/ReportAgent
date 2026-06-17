import { webhooksApi, onError } from "../api.js";
import { mountShell } from "../layout.js";
import { confirmDialog, loadingHtml, showModal, toast } from "../ui.js";
import { formatDate, escapeHtml } from "../utils.js";
import { WEBHOOK_EVENTS } from "../config.js";

export async function renderWebhooks(root) {
  mountShell(root, "Вебхуки", loadingHtml());
  try {
    const list = await webhooksApi.list();
    renderWebhooksTable(root, list);
  } catch (err) {
    onError(err);
  }
}

function webhookForm(wh = null) {
  const events = wh?.events || ["report.completed"];
  const checks = WEBHOOK_EVENTS.map(
    (e) =>
      `<label style="display:flex;gap:.5rem;margin:.25rem 0"><input type="checkbox" name="ev" value="${e}" ${events.includes(e) ? "checked" : ""} /> ${e}</label>`,
  ).join("");
  return `
    <div class="form-group"><label>URL</label><input id="wh-url" type="url" value="${escapeHtml(wh?.url || "")}" required /></div>
    <div class="form-group"><label>События</label>${checks}</div>
    <div class="form-group"><label>Секрет (опц.)</label><input id="wh-secret" type="password" /></div>`;
}

function renderWebhooksTable(root, list) {
  const rows =
    list.length === 0
      ? `<tr><td colspan="5" class="empty-state">Нет вебхуков</td></tr>`
      : list
          .map(
            (w) => `
    <tr>
      <td class="mono" style="max-width:200px;overflow:hidden;text-overflow:ellipsis">${escapeHtml(w.url)}</td>
      <td>${w.events.map((e) => `<span class="badge badge-muted">${e}</span>`).join(" ")}</td>
      <td><label class="switch"><input type="checkbox" data-toggle="${w.id}" ${w.is_active ? "checked" : ""} /><span></span></label></td>
      <td>${formatDate(w.last_triggered_at)}</td>
      <td class="td-actions">
        <button class="btn-icon" data-edit="${w.id}">✏️</button>
        <button class="btn-icon" data-del="${w.id}">🗑</button>
      </td>
    </tr>`,
          )
          .join("");

  mountShell(
    root,
    "Вебхуки",
    `
    <div class="page-header" style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:1rem">
      <div><h1>Вебхуки</h1><p class="seo-lead">POST-уведомления о готовности и ошибках генерации отчётов</p></div>
      <button class="btn" id="btn-register">+ Зарегистрировать</button>
    </div>
    <div class="table-wrap"><table>
      <thead><tr><th>URL</th><th>События</th><th>Активен</th><th>Триггер</th><th></th></tr></thead>
      <tbody>${rows}</tbody>
    </table></div>`,
    (el) => bindWebhooks(el, list),
  );
}

function bindWebhooks(root, list) {
  root.querySelector("#btn-register")?.addEventListener("click", () => openWebhookModal(root, null));

  root.querySelectorAll("[data-edit]").forEach((btn) => {
    const wh = list.find((w) => w.id === btn.dataset.edit);
    btn.onclick = () => openWebhookModal(root, wh);
  });

  root.querySelectorAll("[data-del]").forEach((btn) => {
    btn.onclick = async () => {
      if (!(await confirmDialog("Удалить вебхук?", "URL перестанет получать события."))) return;
      try {
        await webhooksApi.delete(btn.dataset.del);
        toast("Удалено", "success");
        renderWebhooks(root);
      } catch (e) {
        onError(e);
      }
    };
  });

  root.querySelectorAll("[data-toggle]").forEach((input) => {
    input.onchange = async () => {
      try {
        await webhooksApi.update(input.dataset.toggle, { is_active: input.checked });
        toast("Обновлено", "success");
      } catch (e) {
        onError(e);
        input.checked = !input.checked;
      }
    };
  });
}

async function openWebhookModal(root, wh) {
  const body = webhookForm(wh);
  const footer = `<button class="btn btn-outline" data-modal-action="false">Отмена</button><button class="btn" data-modal-action="true">Сохранить</button>`;
  if ((await showModal({ title: wh ? "Редактировать" : "Новый вебхук", body, footer })) !== "true") return;
  const url = document.getElementById("wh-url").value;
  const events = [...document.querySelectorAll('input[name="ev"]:checked')].map((c) => c.value);
  const secret = document.getElementById("wh-secret").value;
  if (!events.length) {
    toast("Выберите событие", "error");
    return;
  }
  const payload = { url, events };
  if (secret) payload.secret = secret;
  try {
    if (wh) await webhooksApi.update(wh.id, payload);
    else await webhooksApi.register(payload);
    toast("Сохранено", "success");
    renderWebhooks(root);
  } catch (e) {
    onError(e);
  }
}
