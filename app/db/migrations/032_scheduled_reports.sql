-- Scheduled reports (cron via Celery Beat)
CREATE TABLE IF NOT EXISTS scheduled_reports (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT 'Scheduled report',
    cron_expression TEXT NOT NULL DEFAULT '0 9 * * 1',
    sheets_url TEXT,
    email TEXT,
    output_format TEXT DEFAULT 'pdf',
    enabled INTEGER NOT NULL DEFAULT 1,
    last_run_at TEXT,
    next_run_at TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_scheduled_reports_user ON scheduled_reports(user_id);
CREATE INDEX IF NOT EXISTS idx_scheduled_reports_next_run ON scheduled_reports(next_run_at);
