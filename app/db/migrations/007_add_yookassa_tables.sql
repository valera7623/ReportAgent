-- YooKassa subscriptions & payments tables
-- SQLite migrations are applied in filename order (schema_migrations table uses filename as a key).

CREATE TABLE IF NOT EXISTS subscriptions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,

    -- Plan types:
    --  - freemium
    --  - premium_monthly
    --  - premium_yearly
    --  - enterprise
    plan_type TEXT NOT NULL DEFAULT 'freemium',
    status TEXT NOT NULL DEFAULT 'active',

    -- Monthly usage control for report generation.
    monthly_reports_limit INTEGER NOT NULL DEFAULT 0,
    used_reports INTEGER NOT NULL DEFAULT 0,
    period_start TIMESTAMP,
    period_end TIMESTAMP,

    -- Access expiration (used to deactivate subscriptions when needed).
    expires_at TIMESTAMP,

    -- YooKassa-specific fields (Step 3 requirement).
    yookassa_payment_id TEXT,
    yookassa_payment_method TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_subscriptions_user_id ON subscriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_status ON subscriptions(status);
CREATE INDEX IF NOT EXISTS idx_subscriptions_plan_type ON subscriptions(plan_type);


CREATE TABLE IF NOT EXISTS payments (
    payment_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    amount INTEGER NOT NULL, -- in kopeks
    currency TEXT DEFAULT 'RUB',

    status TEXT NOT NULL, -- pending/waiting_for_capture/succeeded/canceled
    description TEXT,
    payment_method TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    captured_at TIMESTAMP,
    metadata_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_payments_user_id ON payments(user_id);
CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status);

