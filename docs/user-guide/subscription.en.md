# Subscription & Pricing

ReportAgent uses a freemium model with monthly report limits.

## Plans

| Plan | Reports / month | Notes |
|------|-----------------|-------|
| **Freemium** | 5 | Free |
| **Premium** | 100 | Stripe / YooKassa |
| **Enterprise** | 1000 | Notion, Google Slides |

See `/app#/pricing` for current prices.

## Stripe checkout

```bash
curl -X POST https://your-domain/api/payments/create-checkout \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"price_id":"price_xxx"}'
```

## Current subscription

```bash
curl -H "X-API-Key: $API_KEY" \
  https://your-domain/api/payments/subscription
```

## API

[Payments API](../api/payments.md)
