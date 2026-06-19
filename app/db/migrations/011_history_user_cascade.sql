-- history.user_id lacked ON DELETE CASCADE; rebuild table for safe user deletion.

PRAGMA foreign_keys = OFF;

CREATE TABLE IF NOT EXISTS history_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
    task_id TEXT,
    request_summary TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    request_type TEXT DEFAULT 'api',
    output_format TEXT DEFAULT 'pdf',
    status TEXT DEFAULT 'PENDING',
    duration_seconds REAL
);

INSERT INTO history_new (
    id, user_id, task_id, request_summary, created_at,
    request_type, output_format, status, duration_seconds
)
SELECT
    id, user_id, task_id, request_summary, created_at,
    request_type, output_format, status, duration_seconds
FROM history;

DROP TABLE history;
ALTER TABLE history_new RENAME TO history;

CREATE INDEX IF NOT EXISTS idx_history_user_id ON history(user_id);
CREATE INDEX IF NOT EXISTS idx_history_task_id ON history(task_id);
CREATE INDEX IF NOT EXISTS idx_history_status ON history(status);
CREATE INDEX IF NOT EXISTS idx_history_output_format ON history(output_format);
CREATE INDEX IF NOT EXISTS idx_history_request_type ON history(request_type);

PRAGMA foreign_keys = ON;
