import { API_BASE } from "./config.js";
import { API_KEY_STORAGE } from "./config.js";
import { api } from "./api.js";

function apiKey() {
  const key = localStorage.getItem(API_KEY_STORAGE);
  if (!key) throw new Error("Войдите для скачивания отчёта");
  return key;
}

function downloadPath(taskId, outputFormat = "pdf") {
  return outputFormat === "pdf" ? `/tasks/${taskId}/pdf` : `/tasks/${taskId}/export`;
}

function filenameFromDisposition(header, fallback) {
  if (!header) return fallback;
  const match = /filename\*?=(?:UTF-8''|")?([^";\n]+)/i.exec(header);
  return match ? decodeURIComponent(match[1].replace(/"/g, "")) : fallback;
}

/** Download report file with API key (browser links cannot send X-API-Key). */
export async function downloadReport(taskId, outputFormat = "pdf") {
  const path = downloadPath(taskId, outputFormat);
  const fallbackName = `report_${taskId}.${outputFormat === "excel" ? "xlsx" : outputFormat}`;

  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "X-API-Key": apiKey() },
    redirect: "manual",
  });

  if (res.status === 301 || res.status === 302) {
    const loc = res.headers.get("Location");
    if (loc) {
      window.open(loc, "_blank", "noopener,noreferrer");
      return;
    }
  }

  if (!res.ok) {
    const text = await res.text();
    let message = `HTTP ${res.status}`;
    try {
      const data = JSON.parse(text);
      message = data.detail?.message || data.detail || message;
    } catch {
      if (text) message = text.slice(0, 200);
    }
    throw new Error(typeof message === "string" ? message : "Не удалось скачать отчёт");
  }

  const blob = await res.blob();
  const filename = filenameFromDisposition(res.headers.get("Content-Disposition"), fallbackName);
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(objectUrl);
}

/** Poll Celery task until ready, then download. */
export async function pollTaskAndDownload(taskId, outputFormat = "pdf", { maxAttempts = 120, intervalMs = 2000 } = {}) {
  for (let i = 0; i < maxAttempts; i++) {
    const data = await api(`/tasks/${taskId}`);
    if (data.status === "SUCCESS") {
      await downloadReport(taskId, outputFormat);
      return data;
    }
    if (data.status === "FAILURE") {
      throw new Error(data.error || "Генерация отчёта не удалась");
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
  throw new Error("Превышено время ожидания отчёта");
}

/** Attach click handlers to [data-download-task] buttons. */
export function bindDownloadButtons(root, onError) {
  root.querySelectorAll("[data-download-task]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      try {
        await downloadReport(btn.dataset.downloadTask, btn.dataset.downloadFormat || "pdf");
      } catch (err) {
        onError(err);
      } finally {
        btn.disabled = false;
      }
    });
  });
}
