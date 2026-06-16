-- Stripe integration columns (subscriptions/payments tables created in 007_add_yookassa_tables.sql)

ALTER TABLE subscriptions ADD COLUMN stripe_customer_id TEXT;
ALTER TABLE subscriptions ADD COLUMN stripe_subscription_id TEXT;
ALTER TABLE subscriptions ADD COLUMN payment_provider TEXT DEFAULT 'freemium';

CREATE UNIQUE INDEX IF NOT EXISTS idx_subscriptions_stripe_customer
    ON subscriptions(stripe_customer_id)
    WHERE stripe_customer_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_subscriptions_stripe_subscription
    ON subscriptions(stripe_subscription_id)
    WHERE stripe_subscription_id IS NOT NULL;

ALTER TABLE payments ADD COLUMN provider TEXT DEFAULT 'yookassa';
ALTER TABLE payments ADD COLUMN stripe_payment_intent_id TEXT;
ALTER TABLE payments ADD COLUMN stripe_checkout_session_id TEXT;

CREATE INDEX IF NOT EXISTS idx_payments_provider ON payments(provider);
CREATE INDEX IF NOT EXISTS idx_payments_stripe_pi ON payments(stripe_payment_intent_id);

ALTER TABLE preferences ADD COLUMN last_plan_notification_shown TIMESTAMP;
