import { toast } from "../ui.js";
import { escapeHtml } from "../utils.js";

/**
 * Modal with AI chart/column recommendations before report generation.
 */
export function openAISuggestionsModal({ suggestions, onAccept, onManual, onClose }) {
  const overlay = document.createElement("div");
  overlay.className = "modal-overlay preview-modal-overlay";

  const charts = suggestions.suggested_charts || [];
  const insights = suggestions.insights || [];
  const columns = suggestions.columns || {};
  const description = suggestions.description || "";
  const sourceLabel = suggestions.source === "openai" ? "AI" : "автоанализ";

  const chartsHtml = charts.length
    ? `<ul class="chart-title-list">${charts
        .map(
          (c) =>
            `<li><strong>${escapeHtml(c.title || `${c.type} chart`)}</strong> — ${escapeHtml(c.type)}: ${escapeHtml(c.x)}${c.y ? ` × ${escapeHtml(c.y)}` : ""}</li>`,
        )
        .join("")}</ul>`
    : '<p class="text-muted">Графики будут подобраны автоматически.</p>';

  const insightsHtml = insights.length
    ? `<ul class="ai-insights-list">${insights.map((i) => `<li>${escapeHtml(i)}</li>`).join("")}</ul>`
    : "";

  overlay.innerHTML = `
    <div class="modal modal-xl preview-modal" role="dialog">
      <div class="modal-header">
        <h3>AI-рекомендации <span class="badge badge-muted">${escapeHtml(sourceLabel)}</span></h3>
        <button type="button" class="btn-icon modal-close" aria-label="Закрыть">&times;</button>
      </div>
      <div class="modal-body preview-modal-body">
        ${description ? `<p class="seo-lead">${escapeHtml(description)}</p>` : ""}

        <section class="preview-section">
          <h4>Колонки</h4>
          <div class="preview-stats">
            ${columns.date ? `<div class="preview-stat"><small>Дата</small><strong>${escapeHtml(columns.date)}</strong></div>` : ""}
            ${(columns.numeric || []).map((c) => `<div class="preview-stat"><small>Число</small><strong>${escapeHtml(c)}</strong></div>`).join("")}
            ${(columns.category || []).map((c) => `<div class="preview-stat"><small>Категория</small><strong>${escapeHtml(c)}</strong></div>`).join("")}
          </div>
        </section>

        <section class="preview-section">
          <h4>Мы предлагаем построить</h4>
          ${chartsHtml}
        </section>

        ${insightsHtml ? `<section class="preview-section"><h4>Инсайты</h4>${insightsHtml}</section>` : ""}
      </div>
      <div class="modal-footer preview-modal-footer">
        <button type="button" class="btn btn-outline" data-action="manual">Настроить вручную</button>
        <button type="button" class="btn" data-action="accept">Посмотреть превью</button>
      </div>
    </div>`;

  document.getElementById("modal-root").appendChild(overlay);

  const close = (result) => {
    overlay.remove();
    onClose?.(result);
  };

  overlay.querySelector(".modal-close").onclick = () => close("dismiss");
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) close("dismiss");
  });
  overlay.querySelector(".modal")?.addEventListener("click", (e) => e.stopPropagation());

  overlay.querySelector('[data-action="manual"]').onclick = () => {
    close("manual");
    onManual?.();
  };

  overlay.querySelector('[data-action="accept"]').onclick = async () => {
    const payload = { suggestions };
    close("accepted");
    try {
      await onAccept(payload);
    } catch (err) {
      toast(err.message || "Ошибка создания превью", "error");
    }
  };

  return { close };
}
