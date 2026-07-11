-- Stripe webhook event idempotency (dedup by event.id)
CREATE TABLE IF NOT EXISTS stripe_webhook_events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT,
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
