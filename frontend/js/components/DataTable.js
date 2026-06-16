import { escapeHtml } from "../utils.js";

/**
 * Render scrollable HTML table for preview data (first N rows).
 */
export function renderDataTable(headers, rows, totalRows) {
  if (!headers?.length) {
    return '<p class="text-muted">Нет данных для отображения</p>';
  }

  const headHtml = headers.map((h) => `<th>${escapeHtml(String(h))}</th>`).join("");
  const bodyHtml = (rows || [])
    .map(
      (row) =>
        `<tr>${row
          .map((cell) => `<td>${cell == null ? "" : escapeHtml(String(cell))}</td>`)
          .join("")}</tr>`,
    )
    .join("");

  const more =
    totalRows > rows.length
      ? `<p class="text-muted preview-table-note">Показано ${rows.length} из ${totalRows} строк</p>`
      : "";

  return `
    <div class="preview-table-wrap">
      <table class="preview-table">
        <thead><tr>${headHtml}</tr></thead>
        <tbody>${bodyHtml || '<tr><td colspan="' + headers.length + '">—</td></tr>'}</tbody>
      </table>
    </div>
    ${more}`;
}
