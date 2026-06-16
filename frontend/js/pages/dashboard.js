import { dashboardApi, reportsApi, onError } from "../api.js";
import { mountShell } from "../layout.js";
import { destroyCharts, loadingHtml, registerChart } from "../ui.js";
import { formatDate, formatDuration, formatPercent, escapeHtml, statusClass, truncateId } from "../utils.js";
import { OUTPUT_FORMATS } from "../config.js";

let formatChart = null;

export async function renderDashboard(root) {
  mountShell(root, "Дашборд", loadingHtml());

  try {
    const [stats, reports] = await Promise.all([
      dashboardApi.stats(),
      reportsApi.list({ page: 1, limit: 100 }),
    ]);

    const recent = reports.reports.slice(0, 5);
    const formatCounts = {};
    reports.reports.forEach((r) => {
      const f = r.output_format || "pdf";
      formatCounts[f] = (formatCounts[f] || 0) + 1;
    });

    const recentHtml =
      recent.length === 0
        ? '<p class="empty-state">Отчётов пока нет</p>'
        : recent
            .map(
              (r) => `
          <div class="list-item">
            <div><span class="mono">${truncateId(r.task_id, 12)}</span><br><small class="text-muted">${formatDate(r.created_at)}</small></div>
            <div>
              <span class="badge ${statusClass(r.status)}">${escapeHtml(r.status)}</span>
              <span class="badge badge-muted">${escapeHtml(r.output_format)}</span>
              ${r.status === "SUCCESS" ? `<a class="btn btn-sm btn-outline" href="${r.download_url}" target="_blank">⬇</a>` : ""}
            </div>
          </div>`,
            )
            .join("");

    mountShell(
      root,
      "Дашборд",
      `
      <div class="page-header"><h2>Дашборд</h2><p>Обзор за последние 30 дней</p></div>
      <div class="grid-4" style="margin-bottom:1.5rem">
        <div class="card"><div class="card-body"><small class="text-muted">Отчётов (30 дней)</small><div class="stat-value">${stats.total_reports_last_30_days}</div></div></div>
        <div class="card"><div class="card-body"><small class="text-muted">Успешность</small><div class="stat-value">${formatPercent(stats.success_rate)}</div></div></div>
        <div class="card"><div class="card-body"><small class="text-muted">Популярный формат</small><div class="stat-value">${escapeHtml((stats.most_used_output_format || "pdf").toUpperCase())}</div></div></div>
        <div class="card"><div class="card-body"><small class="text-muted">Среднее время</small><div class="stat-value">${formatDuration(stats.average_generation_time_seconds)}</div></div></div>
      </div>
      <div class="grid-2">
        <div class="card">
          <div class="card-header"><h3>Последние отчёты</h3><a href="#/reports">Все →</a></div>
          <div class="card-body">${recentHtml}</div>
        </div>
        <div class="card">
          <div class="card-header"><h3>Распределение по форматам</h3></div>
          <div class="card-body"><div class="chart-box"><canvas id="format-chart"></canvas></div></div>
        </div>
      </div>`,
      () => drawChart(formatCounts),
    );
  } catch (err) {
    onError(err);
    mountShell(root, "Дашборд", `<p class="text-muted">Не удалось загрузить данные</p>`);
  }
}

function drawChart(counts) {
  destroyCharts();
  const canvas = document.getElementById("format-chart");
  if (!canvas || !window.Chart) return;
  const entries = Object.entries(counts);
  if (!entries.length) return;
  const labels = entries.map(([k]) => OUTPUT_FORMATS.find((f) => f.value === k)?.label || k);
  formatChart = new Chart(canvas, {
    type: "doughnut",
    data: {
      labels,
      datasets: [{ data: entries.map(([, v]) => v), backgroundColor: ["#3b82f6", "#10b981", "#f59e0b", "#8b5cf6", "#ef4444"] }],
    },
    options: { plugins: { legend: { position: "bottom" } } },
  });
  registerChart(formatChart);
}
