-- Optional audit log for preview actions.
CREATE TABLE IF NOT EXISTS preview_log (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    preview_id TEXT,
    action TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_preview_log_user_id ON preview_log(user_id);
CREATE INDEX IF NOT EXISTS idx_preview_log_created_at ON preview_log(created_at);
