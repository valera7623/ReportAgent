-- ReportAgent user memory schema (SQLite)

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    api_key TEXT UNIQUE NOT NULL,
    email TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_used_at TIMESTAMP,
    is_active INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS preferences (
    user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    preferred_chart_type TEXT DEFAULT 'bar',
    theme TEXT DEFAULT 'light',
    default_email TEXT,
    company_logo_url TEXT,
    timezone TEXT DEFAULT 'UTC',
    extra TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT REFERENCES users(id),
    task_id TEXT,
    request_summary TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_history_user_id ON history(user_id);
CREATE INDEX IF NOT EXISTS idx_users_api_key ON users(api_key);
