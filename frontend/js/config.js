/**
 * Базовый URL API. Пустая строка = тот же origin (FastAPI на :8000).
 * Для отдельного хоста: window.REPORTAGENT_API_BASE = 'https://api.example.com';
 */
export const API_BASE = (typeof window !== "undefined" && window.REPORTAGENT_API_BASE) || "";

export const API_KEY_STORAGE = "reportagent_api_key";
export const JWT_STORAGE = "reportagent_jwt";
export const THEME_STORAGE = "reportagent_theme";

export const OUTPUT_FORMATS = [
  { value: "pdf", label: "PDF" },
  { value: "excel", label: "Excel" },
  { value: "pptx", label: "PowerPoint" },
  { value: "notion", label: "Notion" },
  { value: "google_slides", label: "Google Slides" },
];

/** Formats hosted externally (Notion / Google Slides) — open URL, not file download. */
export const EXTERNAL_FORMATS = new Set(["notion", "google_slides"]);

export const EXTERNAL_FORMAT_LABELS = {
  notion: "Notion",
  google_slides: "Google Slides",
};

export const REPORT_STATUSES = ["PENDING", "STARTED", "SUCCESS", "FAILURE", "REVOKED"];

export const WEBHOOK_EVENTS = ["report.completed", "report.failed"];

export const PAGE_SIZE = 20;

export const SERVICE_LABELS = {
  db: "База данных",
  redis: "Redis",
  celery: "Celery",
  chromadb: "ChromaDB",
  openai: "OpenAI",
  disk: "Диск",
};
