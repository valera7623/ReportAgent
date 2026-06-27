import { OUTPUT_FORMATS } from "../config.js";
import { renderDataTable } from "./DataTable.js";
import { createChartCarousel } from "./ChartCarousel.js";
import { toast } from "../ui.js";
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
  const aiSourceLabel =
    data.ai_source === "openai" ? "AI" : data.ai_source === "heuristic" ? "автоанализ" : null;
  const aiDescription = data.ai_description || "";
  const aiInsights = data.ai_insights || [];
  const summaryItems = Object.entries(summary)
    .filter(([, v]) => v != null && v !== "")
    .slice(0, 6)
    .map(([k, v]) => `<div class="preview-stat"><small>${escapeHtml(k)}</small><strong>${escapeHtml(String(v))}</strong></div>`)
    .join("");

  const aiSectionHtml =
    aiDescription || aiInsights.length
      ? `<section class="preview-section">
          <h4>AI-анализ${aiSourceLabel ? ` <span class="badge badge-muted">${escapeHtml(aiSourceLabel)}</span>` : ""}</h4>
          ${aiDescription ? `<p class="seo-lead">${escapeHtml(aiDescription)}</p>` : ""}
          ${
            aiInsights.length
              ? `<ul class="ai-insights-list">${aiInsights.map((i) => `<li>${escapeHtml(i)}</li>`).join("")}</ul>`
              : ""
          }
        </section>`
      : "";

  overlay.innerHTML = `
    <div class="modal modal-xl preview-modal" role="dialog">
      <div class="modal-header">
        <h3>Превью отчёта${aiSourceLabel ? ` <span class="badge badge-muted">${escapeHtml(aiSourceLabel)}</span>` : ""}</h3>
        <button type="button" class="btn-icon modal-close" aria-label="Закрыть">&times;</button>
      </div>
      <div class="modal-body preview-modal-body">
        <p class="text-muted">ID: <span class="mono">${escapeHtml(previewId)}</span>
          ${expiresAt ? ` · до ${escapeHtml(formatDate(expiresAt))}` : ""}</p>

        ${aiSectionHtml}

        <section class="preview-section">
          <h4>Статистика</h4>
          <div class="preview-stats">${summaryItems || '<span class="text-muted">—</span>'}</div>
        </section>

        <section class="preview-section">
          <h4>Графики${(data.charts || []).length ? ` (${data.charts.length})` : ""}</h4>
          ${(data.charts || []).length ? `<ul class="chart-title-list">${(data.charts || []).map((c) => `<li>${escapeHtml(c.title || c.type)} <span class="badge badge-muted">${escapeHtml(c.type)}</span></li>`).join("")}</ul>` : ""}
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
  overlay.querySelector(".modal")?.addEventListener("click", (e) => e.stopPropagation());

  overlay.querySelector('[data-action="edit"]').onclick = (e) => {
    e.stopPropagation();
    close("edit");
  };

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
    } catch (err) {
      toast(err.message || "Ошибка генерации отчёта", "error");
    } finally {
      buttons.forEach((b) => (b.disabled = false));
    }
  };

  overlay.querySelector('[data-action="download"]').onclick = () => runConfirm(false);
  overlay.querySelector('[data-action="send"]').onclick = () => runConfirm(true);

  return { close };
}

export function showPreviewLoading(message = "Генерация превью…") {
  document.getElementById("preview-loading-overlay")?.remove();
  const overlay = document.createElement("div");
  overlay.className = "modal-overlay";
  overlay.id = "preview-loading-overlay";
  overlay.style.zIndex = "9100";
  overlay.innerHTML = `
    <div class="modal" style="max-width:360px;text-align:center">
      <div class="modal-body"><div class="spinner" style="margin:1rem auto"></div><p>${escapeHtml(message)}</p></div>
    </div>`;
  document.getElementById("modal-root").appendChild(overlay);
  return () => overlay.remove();
}
