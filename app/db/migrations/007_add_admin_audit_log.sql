-- Admin audit log for tracking administrative actions.
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_ip TEXT,
    action TEXT NOT NULL,
    target TEXT,
    details TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_audit_log_created_at ON audit_log(created_at);
CREATE INDEX IF NOT EXISTS idx_audit_log_action ON audit_log(action);

-- Per-user and global rate limits (requests per minute).
CREATE TABLE IF NOT EXISTS rate_limits (
    scope_id TEXT PRIMARY KEY,
    limit_per_minute INTEGER NOT NULL DEFAULT 100,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO rate_limits (scope_id, limit_per_minute) VALUES ('__global__', 100);
