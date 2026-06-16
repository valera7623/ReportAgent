import { adminApi, onError } from "../api.js";
import { mountShell } from "../layout.js";
import { confirmDialog, loadingHtml, toast } from "../ui.js";
import {
  formatDate,
  formatPercent,
  formatBytes,
  escapeHtml,
  statusClass,
  healthDot,
} from "../utils.js";
import { SERVICE_LABELS } from "../config.js";
import { navigate } from "../router.js";

/* --- Users list --- */
export async function renderAdminUsers(root) {
  mountShell(root, "Пользователи", loadingHtml());
  const params = new URLSearchParams(location.hash.split("?")[1] || "");
  const is_active = params.get("is_active") || "all";
  const page = Number(params.get("page") || 1);

  try {
    const data = await adminApi.users({ page, limit: 50, is_active });
    const rows = data.users
      .map(
        (u) => `
      <tr class="clickable" data-user="${u.id}">
        <td class="mono">${truncate(u.id)}</td>
        <td>${escapeHtml(u.email || "—")}</td>
        <td>${formatDate(u.created_at)}</td>
        <td>${u.total_requests}</td>
        <td>${formatPercent(u.success_rate)}</td>
        <td><span class="badge ${u.is_active ? "badge-success" : "badge-danger"}">${u.is_active ? "Активен" : "Заблокирован"}</span></td>
        <td class="td-actions" onclick="event.stopPropagation()">
          ${u.is_active ? `<button class="btn-icon" data-block="${u.id}">🔒</button>` : `<button class="btn-icon" data-unblock="${u.id}">🔓</button>`}
          <button class="btn-icon" data-del-user="${u.id}">🗑</button>
        </td>
      </tr>`,
      )
      .join("");

    mountShell(
      root,
      "Пользователи",
      `
      <div class="page-header" style="display:flex;justify-content:space-between;flex-wrap:wrap;gap:1rem">
        <div><h2>Пользователи</h2><p>Управление аккаунтами</p></div>
        <select id="user-filter">
          <option value="all" ${is_active === "all" ? "selected" : ""}>Все</option>
          <option value="true" ${is_active === "true" ? "selected" : ""}>Активные</option>
          <option value="false" ${is_active === "false" ? "selected" : ""}>Заблокированные</option>
        </select>
      </div>
      <div class="table-wrap"><table>
        <thead><tr><th>ID</th><th>Email</th><th>Регистрация</th><th>Запросов</th><th>Успешность</th><th>Статус</th><th></th></tr></thead>
        <tbody>${rows || '<tr><td colspan="7" class="empty-state">Нет данных</td></tr>'}</tbody>
      </table></div>`,
      (el) => {
        el.querySelector("#user-filter").onchange = (e) => {
          location.hash = `#/admin/users?is_active=${e.target.value}&page=1`;
        };
        el.querySelectorAll("[data-user]").forEach((tr) => {
          tr.onclick = () => navigate(`/admin/users/${tr.dataset.user}`);
        });
        el.querySelectorAll("[data-block]").forEach((b) => {
          b.onclick = async () => {
            await adminApi.block(b.dataset.block);
            toast("Заблокирован", "success");
            renderAdminUsers(root);
          };
        });
        el.querySelectorAll("[data-unblock]").forEach((b) => {
          b.onclick = async () => {
            await adminApi.unblock(b.dataset.unblock);
            toast("Разблокирован", "success");
            renderAdminUsers(root);
          };
        });
        el.querySelectorAll("[data-del-user]").forEach((b) => {
          b.onclick = async () => {
            if (!(await confirmDialog("Удалить пользователя?", "Каскадное удаление."))) return;
            await adminApi.deleteUser(b.dataset.delUser);
            toast("Удалён", "success");
            renderAdminUsers(root);
          };
        });
      },
    );
  } catch (e) {
    onError(e);
  }
}

function truncate(id) {
  return id ? `${id.slice(0, 8)}…` : "—";
}

/* --- User detail --- */
export async function renderAdminUserDetail(root, userId) {
  mountShell(root, "Пользователь", loadingHtml());
  try {
    const u = await adminApi.user(userId);
    mountShell(
      root,
      "Пользователь",
      `
      <p><a href="#/admin/users">← Назад</a></p>
      <div class="card" style="margin-bottom:1rem"><div class="card-body">
        <h3>${escapeHtml(u.email || u.id)}</h3>
        <p><strong>ID:</strong> ${u.id}</p>
        <p><strong>Создан:</strong> ${formatDate(u.created_at)}</p>
        <p><strong>Успешность:</strong> ${formatPercent(u.success_rate)}</p>
        <span class="badge ${u.is_active ? "badge-success" : "badge-danger"}">${u.is_active ? "Активен" : "Заблокирован"}</span>
      </div></div>
      <div class="card" style="margin-bottom:1rem"><div class="card-header"><h3>Ключи</h3></div><div class="card-body">
        ${u.api_keys.map((k) => `<div class="mono">${k.key_prefix} — ${escapeHtml(k.name)}</div>`).join("") || "—"}
      </div></div>
      <div class="card" style="margin-bottom:1rem"><div class="card-header"><h3>Последние запросы</h3></div>
        <div class="table-wrap"><table><thead><tr><th>Дата</th><th>Формат</th><th>Статус</th><th>Описание</th></tr></thead>
        <tbody>${u.recent_history.map((h) => `<tr><td>${formatDate(h.created_at)}</td><td>${h.output_format}</td><td><span class="badge ${statusClass(h.status)}">${h.status}</span></td><td>${escapeHtml(h.request_summary)}</td></tr>`).join("")}</tbody></table></div>
      </div>
      <div class="card"><div class="card-header"><h3>Self-healing</h3></div><div class="card-body">
        <p>Успехов: ${u.self_healing.report_successes}, ошибок: ${u.self_healing.report_failures}</p>
        <p class="text-muted">${escapeHtml(u.self_healing.note)}</p>
      </div></div>`,
    );
  } catch (e) {
    onError(e);
  }
}

/* --- Health --- */
let healthTimer = null;

export async function renderAdminHealth(root) {
  mountShell(root, "Здоровье", loadingHtml());
  if (healthTimer) clearInterval(healthTimer);

  async function load() {
    try {
      const [health, metrics] = await Promise.all([adminApi.health(), adminApi.system()]);
      const services = Object.entries(health.services)
        .map(
          ([name, s]) => `
        <div class="card"><div class="card-body">
          <div style="display:flex;justify-content:space-between"><strong>${SERVICE_LABELS[name] || name}</strong><span class="dot ${healthDot(s.status)}"></span></div>
          <span class="badge badge-muted">${s.status}</span>
          ${s.latency_ms != null ? `<p class="text-muted">${s.latency_ms} ms</p>` : ""}
        </div></div>`,
        )
        .join("");

      const cpu = metrics.cpu?.percent ?? 0;
      const ram = metrics.ram?.percent ?? 0;
      const disk = metrics.disk?.percent ?? 0;

      mountShell(
        root,
        "Здоровье",
        `
        <div class="page-header"><h2>Здоровье системы</h2><p>Обновление каждые 30 с · ${formatDate(health.timestamp)}</p></div>
        <p><span class="badge ${health.status === "ok" ? "badge-success" : "badge-warn"}">Статус: ${health.status}</span></p>
        <div class="grid-4" style="margin:1rem 0">${services}</div>
        <div class="grid-4">
          <div class="card"><div class="card-body"><small>CPU</small><div class="gauge"><div class="gauge-fill" style="width:${cpu}%"></div></div><small>${cpu}%</small></div></div>
          <div class="card"><div class="card-body"><small>RAM</small><div class="gauge"><div class="gauge-fill" style="width:${ram}%"></div></div><small>${formatBytes(metrics.ram?.used_bytes)} / ${formatBytes(metrics.ram?.total_bytes)}</small></div></div>
          <div class="card"><div class="card-body"><small>Диск</small><div class="gauge"><div class="gauge-fill" style="width:${disk}%"></div></div><small>Свободно: ${formatBytes(metrics.disk?.free_bytes)}</small></div></div>
        </div>`,
      );
    } catch (e) {
      onError(e);
    }
  }

  await load();
  healthTimer = setInterval(load, 30000);
}

/* --- Celery --- */
export async function renderAdminCelery(root) {
  mountShell(root, "Celery", loadingHtml());
  try {
    const s = await adminApi.celery();
    const workers = s.workers
      .map(
        (w) =>
          `<tr><td class="mono">${escapeHtml(w.name)}</td><td>${w.active}</td><td>${w.reserved}</td><td>${w.processed}</td></tr>`,
      )
      .join("");

    mountShell(
      root,
      "Celery",
      `
      <div class="page-header" style="display:flex;justify-content:space-between;flex-wrap:wrap;gap:1rem">
        <div><h2>Celery</h2><p>Очередь и воркеры</p></div>
        <div>
          <button class="btn btn-danger btn-sm" id="purge" ${s.queue_length === 0 ? "disabled" : ""}>Очистить очередь</button>
          <button class="btn btn-outline btn-sm" id="restart">Перезапустить воркер</button>
        </div>
      </div>
      <div class="card" style="margin-bottom:1rem"><div class="card-body">
        <div class="stat-value">${s.queue_length}</div><small class="text-muted">задач в очереди</small>
      </div></div>
      <div class="table-wrap"><table>
        <thead><tr><th>Воркер</th><th>Активные</th><th>Reserved</th><th>Обработано</th></tr></thead>
        <tbody>${workers || '<tr><td colspan="4" class="empty-state">Нет воркеров</td></tr>'}</tbody>
      </table></div>`,
      (el) => {
        el.querySelector("#purge")?.addEventListener("click", async () => {
          if (!(await confirmDialog("Очистить очередь?", `${s.queue_length} задач будут удалены.`))) return;
          const r = await adminApi.purgeQueue();
          toast(`Удалено: ${r.tasks_removed}`, "success");
          renderAdminCelery(root);
        });
        el.querySelector("#restart")?.addEventListener("click", async () => {
          if (!(await confirmDialog("Перезапустить воркер?", "Docker restart контейнера."))) return;
          const r = await adminApi.restartWorker();
          toast(r.detail || r.status, "success");
        });
      },
    );
  } catch (e) {
    onError(e);
  }
}

/* --- Self-healing --- */
export async function renderAdminSelfHealing(root) {
  mountShell(root, "Self-Healing", loadingHtml());
  try {
    const s = await adminApi.selfHealing();
    const failed = s.total_applications - s.successful_fixes;
    const fixes = (s.top_fixes || [])
      .map(
        (f) =>
          `<tr><td>${escapeHtml(f.error)}</td><td>${f.agent}</td><td>${f.success_count}</td>
          <td><button class="btn-icon" data-delfix="${f.fix_id}">🗑</button></td></tr>`,
      )
      .join("");
    const errors = (s.top_errors || [])
      .slice(0, 5)
      .map((e) => `<div style="display:flex;justify-content:space-between"><span>${escapeHtml(e.error)}</span><span class="badge">${e.count}</span></div>`)
      .join("");

    mountShell(
      root,
      "Self-Healing",
      `
      <div class="page-header" style="display:flex;justify-content:space-between;flex-wrap:wrap;gap:1rem">
        <div><h2>Self-Healing</h2></div>
        <div>
          <button class="btn btn-outline btn-sm" id="seed">Seed-fixes</button>
          <button class="btn btn-outline btn-sm" id="rebuild">Перестроить индекс</button>
        </div>
      </div>
      <div class="grid-4" style="margin-bottom:1rem">
        <div class="card"><div class="card-body"><small>Фиксов</small><div class="stat-value">${s.total_fixes}</div></div></div>
        <div class="card"><div class="card-body"><small>Успешных</small><div class="stat-value">${s.successful_fixes}</div></div></div>
        <div class="card"><div class="card-body"><small>Неудачных</small><div class="stat-value">${failed}</div></div></div>
        <div class="card"><div class="card-body"><small>Успешность</small><div class="stat-value">${formatPercent((s.success_rate || 0) * 100)}</div></div></div>
      </div>
      <div class="card" style="margin-bottom:1rem"><div class="card-header"><h3>Топ ошибок</h3></div><div class="card-body">${errors || "—"}</div></div>
      ${fixes ? `<div class="table-wrap"><table><thead><tr><th>Ошибка</th><th>Агент</th><th>Успехов</th><th></th></tr></thead><tbody>${fixes}</tbody></table></div>` : ""}`,
      (el) => {
        el.querySelector("#seed")?.addEventListener("click", async () => {
          const r = await adminApi.seedFixes();
          toast(`Импорт: ${r.imported}`, "success");
          renderAdminSelfHealing(root);
        });
        el.querySelector("#rebuild")?.addEventListener("click", async () => {
          const r = await adminApi.rebuildIndex();
          toast(`Записей: ${r.records}`, "success");
        });
        el.querySelectorAll("[data-delfix]").forEach((b) => {
          b.onclick = async () => {
            await adminApi.deleteFix(b.dataset.delfix);
            toast("Удалено", "success");
            renderAdminSelfHealing(root);
          };
        });
      },
    );
  } catch (e) {
    onError(e);
  }
}

/* --- Logs --- */
let streamAbort = false;

export async function renderAdminLogs(root) {
  mountShell(root, "Логи", loadingHtml());
  streamAbort = true;

  let level = "";
  let hours = 24;
  let search = "";
  let logs = [];
  let streaming = false;

  async function load() {
    try {
      const data = await adminApi.logs({
        level: level || undefined,
        hours,
        limit: 200,
        search: search || undefined,
      });
      logs = data.logs;
      render();
    } catch (e) {
      onError(e);
    }
  }

  function render() {
    const filtered = search
      ? logs.filter((l) => l.message.toLowerCase().includes(search.toLowerCase()))
      : logs;
    const rows = filtered
      .map(
        (l) => `
      <tr class="log-${(l.level || "").toLowerCase()}">
        <td>${formatDate(l.timestamp)}</td>
        <td><span class="badge ${l.level === "ERROR" ? "badge-danger" : l.level === "WARNING" ? "badge-warn" : "badge-muted"}">${l.level}</span></td>
        <td>${escapeHtml(l.service)}</td>
        <td class="mono" style="max-width:400px;overflow:hidden;text-overflow:ellipsis">${escapeHtml(l.message)}</td>
      </tr>`,
      )
      .join("");

    mountShell(
      root,
      "Логи",
      `
      <div class="card filters">
        <div class="form-row cols-4">
          <div class="form-group"><label>Уровень</label>
            <select id="log-level"><option value="">Все</option><option value="ERROR">ERROR</option><option value="WARNING">WARNING</option><option value="INFO">INFO</option></select>
          </div>
          <div class="form-group"><label>Часы</label>
            <select id="log-hours"><option value="1">1</option><option value="6">6</option><option value="24" selected>24</option><option value="72">72</option></select>
          </div>
          <div class="form-group" style="grid-column:span 2"><label>Поиск</label><input id="log-search" /></div>
        </div>
        <button class="btn btn-outline btn-sm" id="log-refresh">Обновить</button>
        <button class="btn btn-outline btn-sm" id="log-dl">Скачать</button>
        <button class="btn btn-sm" id="log-stream">${streaming ? "Стоп stream" : "Live stream"}</button>
      </div>
      <div class="table-wrap"><table>
        <thead><tr><th>Время</th><th>Уровень</th><th>Сервис</th><th>Сообщение</th></tr></thead>
        <tbody>${rows || '<tr><td colspan="4" class="empty-state">Нет логов</td></tr>'}</tbody>
      </table></div>`,
      (el) => {
        el.querySelector("#log-level").value = level;
        el.querySelector("#log-hours").value = String(hours);
        el.querySelector("#log-search").value = search;
        el.querySelector("#log-level").onchange = (e) => {
          level = e.target.value;
          load();
        };
        el.querySelector("#log-hours").onchange = (e) => {
          hours = Number(e.target.value);
          load();
        };
        el.querySelector("#log-search").oninput = (e) => {
          search = e.target.value;
          render();
        };
        el.querySelector("#log-refresh").onclick = () => load();
        el.querySelector("#log-dl").onclick = async () => {
          const blob = await adminApi.downloadLogs({ level: level || undefined });
          const a = document.createElement("a");
          a.href = URL.createObjectURL(blob);
          a.download = "reportagent-logs.zip";
          a.click();
        };
        el.querySelector("#log-stream").onclick = async () => {
          if (streaming) {
            streamAbort = true;
            streaming = false;
            render();
            return;
          }
          streaming = true;
          streamAbort = false;
          render();
          try {
            for await (const entry of adminApi.streamLogs(level || undefined)) {
              if (streamAbort) break;
              logs.unshift(entry);
              if (logs.length > 500) logs.pop();
              render();
            }
          } catch (e) {
            onError(e);
          }
          streaming = false;
        };
      },
    );
  }

  await load();
}
