# API — Admin

> **Только для администратора.** Все действия логируются в `audit_log`.

## Аутентификация

```http
X-Admin-Key: ваш_admin_ключ
```

Опционально: `ADMIN_ALLOWED_IPS` в `.env`.

## Health

| Method | Path |
|--------|------|
| GET | `/admin/health/all` |
| GET | `/admin/health/system` |

## Пользователи

| Method | Path |
|--------|------|
| GET | `/admin/users?page=1&limit=50&search=` |
| GET | `/admin/users/{user_id}` |
| POST | `/admin/users/{user_id}/block` |
| POST | `/admin/users/{user_id}/unblock` |
| DELETE | `/admin/users/{user_id}` |

## Celery

| Method | Path |
|--------|------|
| GET | `/admin/celery/status` |
| POST | `/admin/celery/purge-queue` |
| POST | `/admin/celery/restart-worker` |

## Self-healing

| Method | Path |
|--------|------|
| GET | `/admin/self-healing/stats` |
| POST | `/admin/self-healing/seed-fixes?overwrite=true` |
| POST | `/admin/self-healing/rebuild-index` |
| DELETE | `/admin/self-healing/fixes/{fix_id}` |

## Логи

| Method | Path |
|--------|------|
| GET | `/admin/logs?level=ERROR&hours=24` |
| GET | `/admin/logs/download` |
| GET | `/admin/logs/stream` (SSE) |

## Метрики

| Method | Path |
|--------|------|
| GET | `/admin/metrics/summary` |
| GET | `/admin/metrics/prometheus` |

## Rate limits

| Method | Path |
|--------|------|
| GET | `/admin/rate-limits` |
| PUT | `/admin/rate-limits/global` |
| PUT | `/admin/rate-limits/user/{user_id}` |

## Webhooks / Payments

| Method | Path |
|--------|------|
| GET | `/admin/webhooks/stats` |
| GET | `/admin/payments/subscriptions` |
| GET | `/admin/payments/revenue` |

## Тест

```bash
ADMIN_API_KEY=your_key python scripts/test_admin_api.py --base-url http://localhost:8000
```

## Генерация ключа

```bash
openssl rand -hex 24
```

Или автоматически при `./deploy.sh`.
