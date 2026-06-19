import { API_BASE, API_KEY_STORAGE, EXTERNAL_FORMAT_LABELS, EXTERNAL_FORMATS } from "./config.js";
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

async function fetchExternalUrl(taskId) {
  const res = await fetch(`${API_BASE}/tasks/${taskId}/export?as_json=1`, {
    headers: { "X-API-Key": apiKey(), Accept: "application/json" },
  });
  const text = await res.text();
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = null;
    }
  }
  if (res.ok && data?.external_url) {
    return data.external_url;
  }

  const task = await api(`/tasks/${taskId}`);
  if (task.status !== "SUCCESS") {
    throw new Error(task.error || "Отчёт ещё не готов");
  }
  const url = task.result?.external_url;
  if (url) return url;

  const message =
    typeof data?.detail === "string"
      ? data.detail
      : data?.detail?.message || `HTTP ${res.status}`;
  throw new Error(message || "Внешняя ссылка на отчёт не найдена");
}

/** Open Notion / Google Slides report in a new tab. */
export async function openExternalReport(taskId, outputFormat = "notion") {
  const url = await fetchExternalUrl(taskId);
  window.open(url, "_blank", "noopener,noreferrer");
  return { external: true, url, outputFormat };
}

/** Download report file or open external URL (Notion / Google Slides). */
export async function downloadReport(taskId, outputFormat = "pdf") {
  if (EXTERNAL_FORMATS.has(outputFormat)) {
    return openExternalReport(taskId, outputFormat);
  }

  const path = downloadPath(taskId, outputFormat);
  const fallbackName = `report_${taskId}.${outputFormat === "excel" ? "xlsx" : outputFormat}`;

  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "X-API-Key": apiKey() },
    redirect: "manual",
  });

  // Cross-origin 302 → opaque redirect (status 0); fall back to JSON export endpoint.
  if (res.status === 301 || res.status === 302) {
    const loc = res.headers.get("Location");
    if (loc) {
      window.open(loc, "_blank", "noopener,noreferrer");
      return { external: true, url: loc, outputFormat };
    }
  }
  if (res.status === 0 || res.type === "opaqueredirect") {
    return openExternalReport(taskId, outputFormat);
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
  return { external: false, outputFormat };
}

/** Poll Celery task until SUCCESS (no download). */
export async function pollTaskUntilSuccess(taskId, { maxAttempts = 120, intervalMs = 2000 } = {}) {
  for (let i = 0; i < maxAttempts; i++) {
    const data = await api(`/tasks/${taskId}`);
    if (data.status === "SUCCESS") return data;
    if (data.status === "FAILURE") {
      throw new Error(data.error || "Генерация отчёта не удалась");
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
  throw new Error("Превышено время ожидания отчёта");
}

/** Poll Celery task until ready, then download or open external link. */
export async function pollTaskAndDownload(taskId, outputFormat = "pdf", { maxAttempts = 120, intervalMs = 2000 } = {}) {
  for (let i = 0; i < maxAttempts; i++) {
    const data = await api(`/tasks/${taskId}`);
    if (data.status === "SUCCESS") {
      const download = await downloadReport(taskId, outputFormat);
      return { ...data, download };
    }
    if (data.status === "FAILURE") {
      throw new Error(data.error || "Генерация отчёта не удалась");
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
  throw new Error("Превышено время ожидания отчёта");
}

export function downloadSuccessMessage(outputFormat, downloadResult) {
  if (downloadResult?.external) {
    const label = EXTERNAL_FORMAT_LABELS[outputFormat] || "внешнем сервисе";
    return `Отчёт открыт в ${label}`;
  }
  return "Файл скачан";
}

/** Attach click handlers to [data-download-task] buttons. */
export function bindDownloadButtons(root, onError, onSuccess) {
  root.querySelectorAll("[data-download-task]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      try {
        const format = btn.dataset.downloadFormat || "pdf";
        const result = await downloadReport(btn.dataset.downloadTask, format);
        if (onSuccess) onSuccess(downloadSuccessMessage(format, result));
      } catch (err) {
        onError(err);
      } finally {
        btn.disabled = false;
      }
    });
  });
}
