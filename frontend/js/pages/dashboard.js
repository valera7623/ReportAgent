import { dashboardApi, paymentsApi, previewApi, reportsApi, onError } from "../api.js";
import { openPreviewModal, showPreviewLoading } from "../components/PreviewModal.js";
import { bindDownloadButtons, pollTaskAndDownload } from "../download.js";
import { mountShell } from "../layout.js";
import { destroyCharts, loadingHtml, registerChart, toast } from "../ui.js";
import {
  formatDate,
  formatDuration,
  formatPercent,
  escapeHtml,
  statusClass,
  truncateId,
  planLabel,
} from "../utils.js";
import { navigate } from "../router.js";
import { OUTPUT_FORMATS } from "../config.js";
import { state } from "../state.js";

let formatChart = null;

export async function renderDashboard(root) {
  mountShell(root, "Дашборд", loadingHtml());

  try {
    const [stats, reports, subscription] = await Promise.all([
      dashboardApi.stats(),
      reportsApi.list({ page: 1, limit: 100 }),
      paymentsApi.subscription().catch(() => null),
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
              ${r.status === "SUCCESS" ? `<button type="button" class="btn btn-sm btn-outline" data-download-task="${escapeHtml(r.task_id)}" data-download-format="${escapeHtml(r.output_format || "pdf")}" title="Скачать">⬇</button>` : ""}
            </div>
          </div>`,
            )
            .join("");

    const sub = subscription || {
      plan_type: "freemium",
      reports_used: 0,
      reports_limit: 5,
      reports_remaining: 5,
      is_active: true,
    };
    const used = sub.reports_used ?? sub.used_reports ?? 0;
    const limit = sub.reports_limit ?? sub.monthly_reports_limit ?? 5;
    const remaining = sub.reports_remaining ?? sub.remaining_reports ?? limit - used;
    const testingMode = !state.billingEnabled || sub.status === "testing";
    const usagePct = !testingMode && limit > 0 ? Math.min(100, Math.round((used / limit) * 100)) : 0;
    const expiresHtml = (sub.current_period_end || sub.expires_at)
      ? `<small class="text-muted">до ${formatDate(sub.current_period_end || sub.expires_at)}</small>`
      : "";
    const planHtml = testingMode
      ? `<div class="stat-value" style="font-size:1.25rem">Тестовый режим</div>
         <small class="text-muted">Лимиты и оплата отключены</small>`
      : `<div class="stat-value" style="font-size:1.25rem">${escapeHtml(planLabel(sub.plan_type))}</div>
         ${expiresHtml}`;
    const usageHtml = testingMode
      ? `<small class="text-muted">Отчёты без ограничений</small>`
      : `<small class="text-muted">Отчёты в этом месяце: ${used} / ${limit}</small>
         <div class="gauge" style="margin-top:.35rem"><div class="gauge-fill" style="width:${usagePct}%"></div></div>
         <small class="text-muted">Осталось: ${remaining}</small>`;
    const pricingBtn = state.billingEnabled
      ? `<button type="button" class="btn btn-outline btn-sm" id="dash-pricing">Управление тарифом</button>`
      : "";

    mountShell(
      root,
      "Дашборд",
      `
      <div class="page-header"><h2>Дашборд</h2><p>Обзор за последние 30 дней</p></div>
      <div class="card" style="margin-bottom:1.5rem">
        <div class="card-header"><h3>Новый отчёт — превью перед отправкой</h3></div>
        <div class="card-body">
          <form id="preview-upload-form">
            <div class="form-group">
              <label>Файл CSV / Excel</label>
              <input type="file" name="file" accept=".csv,.xlsx,.xls" />
            </div>
            <p class="text-muted" style="text-align:center;margin:.75rem 0">или</p>
            <div class="form-group">
              <label>Google Sheets (публичная ссылка)</label>
              <input type="url" name="sheets_url" class="input" placeholder="https://docs.google.com/spreadsheets/d/..." />
            </div>
            <button type="submit" class="btn" id="preview-submit-btn">Создать превью</button>
            <p class="text-muted" style="margin-top:.75rem">Сначала просмотрите таблицу и графики, затем скачайте или отправьте на почту.</p>
          </form>
        </div>
      </div>
      <div class="card" style="margin-bottom:1.5rem">
        <div class="card-body" style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:1rem">
          <div>
            <small class="text-muted">Текущий тариф</small>
            ${planHtml}
          </div>
          <div style="min-width:200px;flex:1;max-width:320px">
            ${usageHtml}
          </div>
          ${pricingBtn}
        </div>
      </div>
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
      (el) => {
        el.querySelector("#dash-pricing")?.addEventListener("click", () => navigate("/pricing"));
        bindDownloadButtons(el, onError);
        bindPreviewForm(el);
        drawChart(formatCounts);
      },
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

async function pollPreviewJob(jobId, hideLoading) {
  for (let i = 0; i < 120; i++) {
    await new Promise((r) => setTimeout(r, 2000));
    const job = await previewApi.jobStatus(jobId);
    if (job.status === "ready") {
      hideLoading();
      return { preview_id: job.preview_id, data: job.data, expires_at: job.expires_at };
    }
    if (job.status === "failed") {
      hideLoading();
      throw new Error(job.error || "Ошибка генерации превью");
    }
  }
  hideLoading();
  throw new Error("Превышено время ожидания превью");
}

function bindPreviewForm(root) {
  const form = root.querySelector("#preview-upload-form");
  if (!form) return;

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(form);
    const file = fd.get("file");
    const sheets = (fd.get("sheets_url") || "").toString().trim();
    const hasFile = file && file.size > 0;

    if (!hasFile && !sheets) {
      toast("Выберите файл или укажите ссылку на Google Sheets", "error");
      return;
    }
    if (hasFile && sheets) {
      toast("Укажите только один источник данных", "error");
      return;
    }

    const submitBtn = form.querySelector("#preview-submit-btn");
    submitBtn.disabled = true;
    let hideLoading = showPreviewLoading(
      hasFile && file.size > 10 * 1024 * 1024 ? "Большой файл — генерация в фоне…" : "Генерация превью…",
    );

    try {
      const uploadFd = new FormData();
      if (hasFile) uploadFd.append("file", file);
      if (sheets) uploadFd.append("sheets_url", sheets);

      let result = await previewApi.create(uploadFd);

      if (result.status === "processing" && result.job_id) {
        result = await pollPreviewJob(result.job_id, hideLoading);
        hideLoading = () => {};
      } else {
        hideLoading();
      }

      openPreviewModal({
        previewId: result.preview_id,
        previewData: { data: result.data, expires_at: result.expires_at },
        onRegenerateChart: async (chartIndex, chartType) => {
          const res = await previewApi.regenerateChart({
            preview_id: result.preview_id,
            chart_index: chartIndex,
            chart_type: chartType,
          });
          return res.image_url;
        },
        onConfirm: async (body) => {
          const resp = await previewApi.confirm(body);
          if (body.email) {
            toast(`Отчёт отправлен на ${body.email}`, "success");
            return;
          }
          setTimeout(async () => {
            const hide = showPreviewLoading("Формирование файла…");
            try {
              await pollTaskAndDownload(resp.task_id, body.output_format);
              toast("Файл скачан", "success");
            } catch (err) {
              onError(err);
            } finally {
              hide();
            }
          }, 0);
        },
        onClose: (action) => {
          if (action === "edit") {
            const card = form.closest(".card");
            card?.scrollIntoView({ behavior: "smooth", block: "center" });
            card?.classList.add("card-highlight");
            setTimeout(() => card?.classList.remove("card-highlight"), 2500);
            toast("Измените файл или ссылку и создайте превью снова");
            const sheetsInput = form.querySelector('[name="sheets_url"]');
            if (sheetsInput?.value) sheetsInput.focus();
            else form.querySelector('[name="file"]')?.focus();
          }
        },
      });
    } catch (err) {
      hideLoading();
      onError(err);
    } finally {
      submitBtn.disabled = false;
    }
  });
}
