import { reportsApi, onError } from "../api.js";
import { bindDownloadButtons } from "../download.js";
import { mountShell } from "../layout.js";
import { confirmDialog, loadingHtml, showModal, toast } from "../ui.js";
import { formatDate, escapeHtml, statusClass, truncateId } from "../utils.js";
import { OUTPUT_FORMATS, REPORT_STATUSES, PAGE_SIZE } from "../config.js";

function getFilters() {
  const hash = location.hash;
  const q = hash.includes("?") ? hash.slice(hash.indexOf("?") + 1) : "";
  const params = new URLSearchParams(q);
  return {
    page: Number(params.get("page") || 1),
    status: params.get("status") || "",
    format: params.get("format") || "",
    dateFrom: params.get("dateFrom") || "",
    dateTo: params.get("dateTo") || "",
  };
}

function setFilters(f) {
  const p = new URLSearchParams();
  if (f.status) p.set("status", f.status);
  if (f.format) p.set("format", f.format);
  if (f.dateFrom) p.set("dateFrom", f.dateFrom);
  if (f.dateTo) p.set("dateTo", f.dateTo);
  p.set("page", String(f.page || 1));
  location.hash = `#/reports?${p}`;
}

function applyFilters(reports, f) {
  return reports.filter((r) => {
    if (f.status && r.status.toUpperCase() !== f.status.toUpperCase()) return false;
    if (f.format && r.output_format !== f.format) return false;
    if (f.dateFrom && new Date(r.created_at) < new Date(f.dateFrom)) return false;
    if (f.dateTo) {
      const to = new Date(f.dateTo);
      to.setHours(23, 59, 59, 999);
      if (new Date(r.created_at) > to) return false;
    }
    return true;
  });
}

export async function renderReports(root) {
  const f = getFilters();
  mountShell(root, "Отчёты", loadingHtml());

  try {
    const hasFilter = f.status || f.format || f.dateFrom || f.dateTo;
    const data = await reportsApi.list({
      page: hasFilter ? 1 : f.page,
      limit: hasFilter ? 100 : PAGE_SIZE,
    });
    const filtered = hasFilter ? applyFilters(data.reports, f) : data.reports;
    const total = hasFilter ? filtered.length : data.total;
    const page = f.page;
    const pageReports = hasFilter
      ? filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)
      : filtered;
    const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

    const filtersHtml = `
      <div class="card filters">
        <div class="form-row cols-4">
          <div class="form-group"><label>Статус</label>
            <select id="f-status"><option value="">Все</option>${REPORT_STATUSES.map((s) => `<option value="${s}" ${f.status === s ? "selected" : ""}>${s}</option>`).join("")}</select>
          </div>
          <div class="form-group"><label>Формат</label>
            <select id="f-format"><option value="">Все</option>${OUTPUT_FORMATS.map((o) => `<option value="${o.value}" ${f.format === o.value ? "selected" : ""}>${o.label}</option>`).join("")}</select>
          </div>
          <div class="form-group"><label>Дата от</label><input type="date" id="f-from" value="${f.dateFrom}" /></div>
          <div class="form-group"><label>Дата до</label><input type="date" id="f-to" value="${f.dateTo}" /></div>
        </div>
        <button type="button" class="btn btn-outline btn-sm" id="f-reset">Сбросить</button>
      </div>`;

    const rows =
      pageReports.length === 0
        ? `<tr><td colspan="5" class="empty-state">Не найдено</td></tr>`
        : pageReports
            .map(
              (r) => `
        <tr>
          <td class="mono">${truncateId(r.task_id, 10)}</td>
          <td>${formatDate(r.created_at)}</td>
          <td><span class="badge badge-muted">${escapeHtml(r.output_format)}</span></td>
          <td><span class="badge ${statusClass(r.status)}">${escapeHtml(r.status)}</span></td>
          <td class="td-actions">
            ${r.status === "SUCCESS" ? `<button type="button" class="btn-icon" data-download-task="${escapeHtml(r.task_id)}" data-download-format="${escapeHtml(r.output_format || "pdf")}" title="Скачать">⬇</button>` : ""}
            <button class="btn-icon" data-retry="${r.task_id}" data-format="${escapeHtml(r.output_format)}" data-summary="${escapeHtml(r.request_summary)}" title="Повторить">🔄</button>
            <button class="btn-icon" data-delete="${r.task_id}" title="Удалить">🗑</button>
          </td>
        </tr>`,
            )
            .join("");

    mountShell(
      root,
      "Отчёты",
      `
      <div class="page-header"><h1>Отчёты</h1><p class="seo-lead">История генерации отчётов: статус, формат и скачивание</p></div>
      ${filtersHtml}
      <div class="table-wrap"><table>
        <thead><tr><th>ID</th><th>Дата</th><th>Формат</th><th>Статус</th><th></th></tr></thead>
        <tbody>${rows}</tbody>
      </table></div>
      <div class="pagination">
        <span>Стр. ${page} / ${totalPages}</span>
        <div>
          <button class="btn btn-outline btn-sm" id="prev" ${page <= 1 ? "disabled" : ""}>Назад</button>
          <button class="btn btn-outline btn-sm" id="next" ${page >= totalPages ? "disabled" : ""}>Вперёд</button>
        </div>
      </div>`,
      (el) => bindReports(el, f),
    );
  } catch (err) {
    onError(err);
  }
}

function bindReports(root, f) {
  const apply = () => {
    setFilters({
      status: root.querySelector("#f-status").value,
      format: root.querySelector("#f-format").value,
      dateFrom: root.querySelector("#f-from").value,
      dateTo: root.querySelector("#f-to").value,
      page: 1,
    });
  };
  ["#f-status", "#f-format", "#f-from", "#f-to"].forEach((sel) => {
    root.querySelector(sel)?.addEventListener("change", apply);
  });
  root.querySelector("#f-reset")?.addEventListener("click", () => setFilters({ page: 1 }));
  root.querySelector("#prev")?.addEventListener("click", () => setFilters({ ...f, page: f.page - 1 }));
  root.querySelector("#next")?.addEventListener("click", () => setFilters({ ...f, page: f.page + 1 }));
  bindDownloadButtons(root, onError);

  root.querySelectorAll("[data-delete]").forEach((btn) => {
    btn.onclick = async () => {
      if (!(await confirmDialog("Удалить отчёт?", "Файлы и запись истории будут удалены."))) return;
      try {
        await reportsApi.delete(btn.dataset.delete);
        toast("Удалено", "success");
        renderReports(root);
      } catch (e) {
        onError(e);
      }
    };
  });

  root.querySelectorAll("[data-retry]").forEach((btn) => {
    btn.onclick = async () => {
      const formatOpts = OUTPUT_FORMATS.map(
        (o) => `<option value="${o.value}" ${o.value === btn.dataset.format ? "selected" : ""}>${o.label}</option>`,
      ).join("");
      const body = `
        <p class="text-muted">${escapeHtml(btn.dataset.summary)}</p>
        <div class="form-group"><label>Email</label><input id="retry-email" type="email" /></div>
        <div class="form-group"><label>Google Sheets URL</label><input id="retry-sheets" /></div>
        <div class="form-group"><label>Формат</label><select id="retry-format">${formatOpts}</select></div>`;
      const footer = `<button class="btn btn-outline" data-modal-action="false">Отмена</button><button class="btn" data-modal-action="true">Повторить</button>`;
      if ((await showModal({ title: "Повторить генерацию", body, footer })) !== "true") return;
      const fd = new FormData();
      const email = document.getElementById("retry-email")?.value;
      const sheets = document.getElementById("retry-sheets")?.value;
      const fmt = document.getElementById("retry-format")?.value;
      if (email) fd.append("email", email);
      if (sheets) fd.append("sheets_url", sheets);
      fd.append("output_format", fmt);
      try {
        await reportsApi.retry(fd);
        toast("Задача в очереди", "success");
      } catch (e) {
        onError(e);
      }
    };
  });
}
