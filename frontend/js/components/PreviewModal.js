import { OUTPUT_FORMATS } from "../config.js";
import { renderDataTable } from "./DataTable.js";
import { createChartCarousel } from "./ChartCarousel.js";
import { escapeHtml, formatDate } from "../utils.js";

/**
 * Full-screen preview modal: table, stats, charts, confirm actions.
 */
export function openPreviewModal({
  previewData,
  previewId,
  onConfirm,
  onRegenerateChart,
  onClose,
}) {
  const overlay = document.createElement("div");
  overlay.className = "modal-overlay preview-modal-overlay";

  const { data, expires_at: expiresAt } = previewData;
  const summary = data.summary || {};
  const summaryItems = Object.entries(summary)
    .filter(([, v]) => v != null && v !== "")
    .slice(0, 6)
    .map(([k, v]) => `<div class="preview-stat"><small>${escapeHtml(k)}</small><strong>${escapeHtml(String(v))}</strong></div>`)
    .join("");

  overlay.innerHTML = `
    <div class="modal modal-xl preview-modal" role="dialog">
      <div class="modal-header">
        <h3>Превью отчёта</h3>
        <button type="button" class="btn-icon modal-close" aria-label="Закрыть">&times;</button>
      </div>
      <div class="modal-body preview-modal-body">
        <p class="text-muted">ID: <span class="mono">${escapeHtml(previewId)}</span>
          ${expiresAt ? ` · до ${escapeHtml(formatDate(expiresAt))}` : ""}</p>

        <section class="preview-section">
          <h4>Статистика</h4>
          <div class="preview-stats">${summaryItems || '<span class="text-muted">—</span>'}</div>
        </section>

        <section class="preview-section">
          <h4>Графики</h4>
          <div id="preview-charts-mount"></div>
        </section>

        <section class="preview-section">
          <h4>Данные</h4>
          ${renderDataTable(data.headers, data.rows, data.total_rows)}
        </section>

        <section class="preview-section preview-confirm">
          <label>Email (опционально)</label>
          <input type="email" id="preview-email" class="input" placeholder="user@example.com" />
          <label>Формат</label>
          <select id="preview-format" class="input">
            ${OUTPUT_FORMATS.map((f) => `<option value="${f.value}">${escapeHtml(f.label)}</option>`).join("")}
          </select>
        </section>
      </div>
      <div class="modal-footer preview-modal-footer">
        <button type="button" class="btn btn-outline" data-action="edit">Редактировать</button>
        <button type="button" class="btn btn-outline" data-action="download">Скачать</button>
        <button type="button" class="btn" data-action="send">Отправить на почту</button>
      </div>
    </div>`;

  document.getElementById("modal-root").appendChild(overlay);

  const chartsMount = overlay.querySelector("#preview-charts-mount");
  const carousel = createChartCarousel(data.charts || [], previewId, onRegenerateChart);
  chartsMount.appendChild(carousel);

  const close = (result) => {
    overlay.remove();
    if (onClose) onClose(result);
  };

  overlay.querySelector(".modal-close").onclick = () => close(false);
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) close(false);
  });

  overlay.querySelector('[data-action="edit"]').onclick = () => close("edit");

  const runConfirm = async (withEmail) => {
    const emailEl = overlay.querySelector("#preview-email");
    const formatEl = overlay.querySelector("#preview-format");
    const email = withEmail ? emailEl.value.trim() : "";
    if (withEmail && !email) {
      emailEl.focus();
      return;
    }
    const buttons = overlay.querySelectorAll(".preview-modal-footer button");
    buttons.forEach((b) => (b.disabled = true));
    try {
      await onConfirm({
        preview_id: previewId,
        email: withEmail ? email : null,
        output_format: formatEl.value,
      });
      close("confirmed");
    } finally {
      buttons.forEach((b) => (b.disabled = false));
    }
  };

  overlay.querySelector('[data-action="download"]').onclick = () => runConfirm(false);
  overlay.querySelector('[data-action="send"]').onclick = () => runConfirm(true);

  return { close };
}

export function showPreviewLoading(message = "Генерация превью…") {
  const overlay = document.createElement("div");
  overlay.className = "modal-overlay";
  overlay.id = "preview-loading-overlay";
  overlay.innerHTML = `
    <div class="modal" style="max-width:360px;text-align:center">
      <div class="modal-body"><div class="spinner" style="margin:1rem auto"></div><p>${escapeHtml(message)}</p></div>
    </div>`;
  document.getElementById("modal-root").appendChild(overlay);
  return () => overlay.remove();
}
