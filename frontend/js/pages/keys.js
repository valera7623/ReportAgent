import { keysApi, onError } from "../api.js";
import { mountShell } from "../layout.js";
import { confirmDialog, loadingHtml, showModal, toast } from "../ui.js";
import { formatDate, escapeHtml } from "../utils.js";

export async function renderKeys(root) {
  mountShell(root, "API-ключи", loadingHtml());
  try {
    const data = await keysApi.list();
    renderKeysTable(root, data.keys);
  } catch (err) {
    onError(err);
  }
}

function renderKeysTable(root, keys) {
  const rows =
    keys.length === 0
      ? `<tr><td colspan="6" class="empty-state">Нет ключей</td></tr>`
      : keys
          .map(
            (k) => `
    <tr>
      <td class="mono">${escapeHtml(k.key_prefix)}${k.is_current ? ' <span class="badge">Текущий</span>' : ""}</td>
      <td><span class="key-name" data-id="${k.id}">${escapeHtml(k.name)}</span></td>
      <td>${formatDate(k.created_at)}</td>
      <td>${formatDate(k.last_used_at)}</td>
      <td><span class="badge ${k.is_active ? "badge-success" : "badge-danger"}">${k.is_active ? "Активен" : "Отозван"}</span></td>
      <td class="td-actions">
        <button class="btn-icon" data-rename="${k.id}" data-name="${escapeHtml(k.name)}">✏️</button>
        <button class="btn-icon" data-rotate="${k.id}" data-prefix="${escapeHtml(k.key_prefix)}" ${!k.is_active ? "disabled" : ""}>🔄</button>
        <button class="btn-icon" data-revoke="${k.id}" data-prefix="${escapeHtml(k.key_prefix)}" ${!k.is_active ? "disabled" : ""}>🗑</button>
      </td>
    </tr>`,
          )
          .join("");

  mountShell(
    root,
    "API-ключи",
    `
    <div class="page-header" style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:1rem">
      <div><h2>API-ключи</h2><p>Управление ключами доступа</p></div>
      <button class="btn" id="btn-generate">+ Сгенерировать</button>
    </div>
    <div class="table-wrap"><table>
      <thead><tr><th>Префикс</th><th>Название</th><th>Создан</th><th>Использован</th><th>Статус</th><th></th></tr></thead>
      <tbody>${rows}</tbody>
    </table></div>`,
    (el) => bindKeys(el),
  );
}

function bindKeys(root) {
  root.querySelector("#btn-generate")?.addEventListener("click", async () => {
    const body = `<div class="form-group"><label>Название</label><input id="gen-name" value="Default" /></div>`;
    const footer = `<button class="btn btn-outline" data-modal-action="false">Отмена</button><button class="btn" data-modal-action="true">Сгенерировать</button>`;
    if ((await showModal({ title: "Новый ключ", body, footer })) !== "true") return;
    const name = document.getElementById("gen-name")?.value || "Default";
    try {
      const res = await keysApi.generate({ name });
      await showModal({
        title: "Сохраните ключ!",
        body: `<p class="text-muted" style="color:var(--danger)">Показывается один раз.</p><input readonly value="${escapeHtml(res.key)}" onclick="this.select()" />`,
        footer: `<button class="btn" data-modal-action="true">Готово</button>`,
      });
      renderKeys(root);
    } catch (e) {
      onError(e);
    }
  });

  root.querySelectorAll("[data-revoke]").forEach((btn) => {
    btn.onclick = async () => {
      if (!(await confirmDialog("Отозвать ключ?", `Префикс ${btn.dataset.prefix}`))) return;
      try {
        await keysApi.revoke(btn.dataset.revoke);
        toast("Ключ отозван", "success");
        renderKeys(root);
      } catch (e) {
        onError(e);
      }
    };
  });

  root.querySelectorAll("[data-rename]").forEach((btn) => {
    btn.onclick = async () => {
      const body = `<div class="form-group"><label>Название</label><input id="rename-val" value="${btn.dataset.name}" /></div>`;
      const footer = `<button class="btn btn-outline" data-modal-action="false">Отмена</button><button class="btn" data-modal-action="true">Сохранить</button>`;
      if ((await showModal({ title: "Переименовать", body, footer })) !== "true") return;
      try {
        await keysApi.rename(btn.dataset.rename, document.getElementById("rename-val").value);
        toast("Переименовано", "success");
        renderKeys(root);
      } catch (e) {
        onError(e);
      }
    };
  });

  root.querySelectorAll("[data-rotate]").forEach((btn) => {
    btn.onclick = async () => {
      const body = `<div class="form-group"><label>Название нового ключа</label><input id="rot-name" placeholder="Production (rotated)" /></div>`;
      const footer = `<button class="btn btn-outline" data-modal-action="false">Отмена</button><button class="btn" data-modal-action="true">Ротировать</button>`;
      if ((await showModal({ title: `Ротация ${btn.dataset.prefix}`, body, footer })) !== "true") return;
      try {
        const name = document.getElementById("rot-name")?.value;
        const res = await keysApi.rotate(btn.dataset.rotate, name ? { new_name: name } : {});
        await showModal({
          title: "Новый ключ",
          body: `<input readonly value="${escapeHtml(res.new_key)}" onclick="this.select()" />`,
          footer: `<button class="btn" data-modal-action="true">Готово</button>`,
        });
        renderKeys(root);
      } catch (e) {
        onError(e);
      }
    };
  });
}
