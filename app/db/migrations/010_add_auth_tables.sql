-- Email/password authentication columns for users table.
-- Note: api_key remains NOT NULL, auth-only users get placeholder pending_<user_id>.

ALTER TABLE users ADD COLUMN password_hash TEXT;
ALTER TABLE users ADD COLUMN is_verified INTEGER DEFAULT 0;
ALTER TABLE users ADD COLUMN verification_token TEXT;
ALTER TABLE users ADD COLUMN verification_token_expires_at TIMESTAMP;
ALTER TABLE users ADD COLUMN reset_password_token TEXT;
ALTER TABLE users ADD COLUMN reset_password_token_expires_at TIMESTAMP;
ALTER TABLE users ADD COLUMN last_login_at TIMESTAMP;
ALTER TABLE users ADD COLUMN login_attempts INTEGER DEFAULT 0;
ALTER TABLE users ADD COLUMN locked_until TIMESTAMP;

-- Unique email where set (email column existed from 001_init.sql)
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_unique ON users(email) WHERE email IS NOT NULL;

-- Existing API-key users are treated as verified (no email/password yet)
UPDATE users
SET is_verified = 1
WHERE password_hash IS NULL
  AND api_key IS NOT NULL
  AND api_key NOT LIKE 'pending_%';
