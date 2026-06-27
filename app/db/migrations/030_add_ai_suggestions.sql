-- AI suggestions cache (per user + file hash, TTL 24h)

CREATE TABLE IF NOT EXISTS ai_suggestions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    file_hash TEXT NOT NULL,
    suggestions TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ai_suggestions_user_hash ON ai_suggestions(user_id, file_hash);
CREATE INDEX IF NOT EXISTS idx_ai_suggestions_expires ON ai_suggestions(expires_at);
