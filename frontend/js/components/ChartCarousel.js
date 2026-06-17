import { API_BASE } from "../config.js";
import { API_KEY_STORAGE } from "../config.js";
import { escapeHtml } from "../utils.js";

async function fetchChartBlob(imagePath) {
  const base = API_BASE || "";
  const url = imagePath.startsWith("http") ? imagePath : `${base}${imagePath}`;
  const key = localStorage.getItem(API_KEY_STORAGE);
  const res = await fetch(url, { headers: key ? { "X-API-Key": key } : {} });
  if (!res.ok) throw new Error("Chart load failed");
  return URL.createObjectURL(await res.blob());
}

/**
 * Chart carousel with type switcher (loads PNG via authenticated fetch).
 */
export function createChartCarousel(charts, previewId, onRegenerate) {
  const container = document.createElement("div");
  container.className = "chart-carousel";
  container.dataset.previewId = previewId;

  if (!charts?.length) {
    container.innerHTML = '<p class="text-muted">Графики не сгенерированы</p>';
    return container;
  }

  const slidesEl = document.createElement("div");
  slidesEl.className = "chart-slides";

  charts.forEach((chart, idx) => {
    const slide = document.createElement("div");
    slide.className = `chart-slide${idx === 0 ? " active" : ""}`;
    slide.dataset.slide = String(idx);
    slide.innerHTML = `
      <div class="chart-img-wrap"><div class="spinner chart-spinner"></div></div>
      <div class="chart-slide-meta">
        <strong>${escapeHtml(chart.title)}</strong>
        <span class="badge badge-muted">${escapeHtml(chart.type)}</span>
      </div>
      <div class="chart-type-btns">
        ${["bar", "line", "pie"]
          .map(
            (t) =>
              `<button type="button" class="btn btn-sm btn-outline chart-type-btn" data-chart-type="${t}" ${chart.type === t ? "disabled" : ""}>${t}</button>`,
          )
          .join("")}
      </div>`;
    slidesEl.appendChild(slide);

    const imgWrap = slide.querySelector(".chart-img-wrap");
    fetchChartBlob(chart.image_url)
      .then((blobUrl) => {
        imgWrap.innerHTML = `<img src="${blobUrl}" alt="${escapeHtml(chart.title)}" class="preview-chart-img" loading="lazy" decoding="async" />`;
      })
      .catch((err) => {
        console.error("Chart load failed:", chart.image_url, err);
        imgWrap.innerHTML = '<p class="text-muted">Не удалось загрузить график. Обновите страницу и попробуйте снова.</p>';
      });
  });

  const dotsEl = document.createElement("div");
  dotsEl.className = "chart-dots";
  charts.forEach((_, idx) => {
    const dot = document.createElement("button");
    dot.type = "button";
    dot.className = `chart-dot ${idx === 0 ? "active" : ""}`;
    dot.dataset.goto = String(idx);
    dot.setAttribute("aria-label", `Chart ${idx + 1}`);
    dotsEl.appendChild(dot);
  });

  container.append(slidesEl, dotsEl);

  const slides = () => container.querySelectorAll(".chart-slide");
  const dots = () => container.querySelectorAll(".chart-dot");

  const show = (idx) => {
    slides().forEach((s, i) => {
      s.classList.toggle("active", i === idx);
    });
    dots().forEach((d, i) => d.classList.toggle("active", i === idx));
  };

  dots().forEach((dot) => {
    dot.addEventListener("click", () => show(Number(dot.dataset.goto)));
  });

  container.querySelectorAll(".chart-slide").forEach((slide, chartIndex) => {
    slide.querySelectorAll(".chart-type-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        if (!onRegenerate) return;
        btn.disabled = true;
        try {
          const imageUrl = await onRegenerate(chartIndex, btn.dataset.chartType);
          const imgWrap = slide.querySelector(".chart-img-wrap");
          const blobUrl = await fetchChartBlob(imageUrl);
          imgWrap.innerHTML = `<img src="${blobUrl}" alt="${escapeHtml(chart.title || "График отчёта")}" class="preview-chart-img" loading="lazy" decoding="async" />`;
          slide.querySelectorAll(".chart-type-btn").forEach((b) => {
            b.disabled = b.dataset.chartType === btn.dataset.chartType;
          });
          const badge = slide.querySelector(".badge");
          if (badge) badge.textContent = btn.dataset.chartType;
        } finally {
          btn.disabled = false;
        }
      });
    });
  });

  return container;
}

export async function reloadChartImage(slide, imagePath) {
  const imgWrap = slide.querySelector(".chart-img-wrap");
  if (!imgWrap) return;
  imgWrap.innerHTML = '<div class="spinner chart-spinner"></div>';
  try {
    const blobUrl = await fetchChartBlob(imagePath);
    imgWrap.innerHTML = `<img src="${blobUrl}" alt="График отчёта ReportAgent" class="preview-chart-img" loading="lazy" decoding="async" />`;
  } catch {
    imgWrap.innerHTML = '<p class="text-muted">Ошибка загрузки</p>';
  }
}
