# API — Платежи

## Stripe (основной)

| Method | Path | Auth | Описание |
|--------|------|------|----------|
| GET | `/api/payments/prices` | нет | Каталог тарифов |
| POST | `/api/payments/create-checkout` | X-API-Key | Checkout Session |
| GET | `/api/payments/subscription` | X-API-Key | Текущая подписка |
| POST | `/api/payments/cancel-subscription` | X-API-Key | Отмена |
| POST | `/webhooks/stripe` | нет | Webhook Stripe |

```bash
curl -X POST https://ваш-домен/api/payments/create-checkout \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"price_id":"price_xxx"}'
```

## ЮKassa (РФ, опционально)

| Method | Path | Auth |
|--------|------|------|
| POST | `/api/payments/yookassa/create` | X-API-Key |
| GET | `/api/payments/yookassa/status/{id}` | X-API-Key |
| POST | `/webhooks/yookassa` | нет |

```bash
curl -X POST https://ваш-домен/api/payments/yookassa/create \
  -H "X-API-Key: $API_KEY" \
  -d '{"plan_type":"premium_monthly"}'
```

## Admin

| Method | Path |
|--------|------|
| GET | `/admin/payments/subscriptions` |
| GET | `/admin/payments/revenue` |
| POST | `/admin/payments/refund/{payment_id}` |

## Лимиты

| План | Отчётов / месяц |
|------|-----------------|
| Freemium | 5 |
| Premium | 100 |
| Enterprise | 1000 |

При превышении — HTTP **402**.

## Тестовые карты Stripe

| Карта | Результат |
|-------|-----------|
| `4242 4242 4242 4242` | Успех |
| `4000 0000 0000 0002` | Отклонена |
