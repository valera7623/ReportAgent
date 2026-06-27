# API — Payments

## Stripe (primary)

| Method | Path | Auth |
|--------|------|------|
| GET | `/api/payments/prices` | none |
| POST | `/api/payments/create-checkout` | X-API-Key |
| GET | `/api/payments/subscription` | X-API-Key |
| POST | `/webhooks/stripe` | none |

## YooKassa (optional, RU)

| Method | Path |
|--------|------|
| POST | `/api/payments/yookassa/create` |
| POST | `/webhooks/yookassa` |

## Limits

Freemium: 5, Premium: 100, Enterprise: 1000 reports/month. Exceeded → HTTP **402**.
