# Подписка и тарифы

ReportAgent использует модель freemium с лимитами на количество отчётов в месяц.

## Тарифы

| План | Лимит отчётов / месяц | Особенности |
|------|------------------------|-------------|
| **Freemium** | 5 | Бесплатно |
| **Premium** | 100 | Stripe / ЮKassa |
| **Enterprise** | 1000 | Notion, Google Slides |

Точные цены — на странице `/app#/pricing`.

## Оплата (Stripe — основной)

1. Откройте `/app#/pricing`
2. Выберите план → редирект на Stripe Checkout
3. После оплаты — `/app#/success`
4. Лимиты обновляются автоматически через webhook

API:

```bash
curl -X POST https://ваш-домен/api/payments/create-checkout \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"price_id":"price_xxx"}'
```

## Оплата (ЮKassa — РФ)

```bash
curl -X POST https://ваш-домен/api/payments/yookassa/create \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"plan_type":"premium_monthly"}'
```

Ответ содержит `confirmation_url` для оплаты.

## Текущая подписка

```bash
curl -H "X-API-Key: $API_KEY" \
  https://ваш-домен/api/payments/subscription
```

Веб: `/app#/subscription`

## Отмена подписки

```bash
curl -X POST https://ваш-домен/api/payments/cancel-subscription \
  -H "X-API-Key: $API_KEY"
```

## Превышение лимита

При исчерпании лимита API возвращает **402 Payment Required** с информацией о тарифе.

## API

[API платежей](../api/payments.md)
