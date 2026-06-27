# API — Webhooks

Исходящие POST-уведомления при завершении или ошибке генерации отчёта.

## События

| Событие | Когда |
|---------|-------|
| `report.completed` | Отчёт успешно сгенерирован |
| `report.failed` | Ошибка в pipeline |

## POST /api/webhooks/register

```bash
curl -X POST https://ваш-домен/api/webhooks/register \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://myapp.com/callback",
    "events": ["report.completed", "report.failed"],
    "secret": "my-hmac-secret"
  }'
```

## GET /api/webhooks

Список зарегистрированных webhooks.

## PUT /api/webhooks/{id}

Обновить URL или events.

## DELETE /api/webhooks/{id}

Удалить webhook.

## POST /api/webhooks/{id}/reactivate

Включить после автоматической деактивации (5+ неудач).

## Payload

```json
{
  "event": "report.completed",
  "task_id": "uuid",
  "status": "SUCCESS",
  "download_url": "https://reportagent.example.com/tasks/uuid/export",
  "output_format": "pdf",
  "timestamp": "2026-01-15T10:30:00Z",
  "user_id": "a1b2c3d4",
  "metadata": {"source_type": "file", "duration_seconds": 12.5}
}
```

## Подпись HMAC

Заголовок `X-Webhook-Signature` = HMAC-SHA256(secret, canonical JSON).

```python
import hashlib, hmac, json

def verify(secret, body, signature):
    payload = json.dumps(body, separators=(",", ":"), sort_keys=True)
    expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
```

## Admin

`GET /admin/webhooks/stats` — статистика (X-Admin-Key).
