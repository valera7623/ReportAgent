# Схема базы данных

ReportAgent использует **SQLite** (`app/data/users.db`). Миграции: `app/db/migrations/*.sql`.

## Таблицы

### `users`

| Колонка | Тип | Описание |
|---------|-----|----------|
| `id` | TEXT PK | UUID пользователя |
| `api_key` | TEXT | Legacy ключ (deprecated) |
| `email` | TEXT | Email |
| `password_hash` | TEXT | bcrypt hash |
| `is_verified` | INTEGER | Email подтверждён |
| `created_at` | TIMESTAMP | |
| `last_used_at` | TIMESTAMP | |
| `is_active` | INTEGER | 0 = заблокирован |

### `api_keys`

Несколько ключей на пользователя (SHA-256 hash).

| Колонка | Тип | Описание |
|---------|-----|----------|
| `id` | TEXT PK | UUID ключа |
| `user_id` | TEXT FK | → users |
| `key_hash` | TEXT | SHA-256 |
| `key_prefix` | TEXT | Первые 8 символов |
| `name` | TEXT | Имя ключа |
| `expires_at` | TIMESTAMP | NULL = бессрочный |
| `is_active` | INTEGER | |

### `preferences`

| Колонка | Тип | Описание |
|---------|-----|----------|
| `user_id` | TEXT PK FK | |
| `preferred_chart_type` | TEXT | bar/line/pie |
| `theme` | TEXT | light/dark |
| `default_email` | TEXT | |
| `default_output_format` | TEXT | pdf/excel/… |
| `company_logo_url` | TEXT | |
| `timezone` | TEXT | |

### `history`

| Колонка | Тип | Описание |
|---------|-----|----------|
| `id` | INTEGER PK | |
| `user_id` | TEXT FK | |
| `task_id` | TEXT | Celery task ID |
| `request_summary` | TEXT | |
| `status` | TEXT | PENDING/SUCCESS/FAILURE |
| `output_format` | TEXT | |
| `duration_seconds` | REAL | |
| `request_type` | TEXT | api/voice |

### `subscriptions` / `payments`

Биллинг Stripe и ЮKassa — см. миграции `007_add_yookassa_tables.sql`, `008_add_stripe_integration.sql`.

### `webhooks`

Зарегистрированные URL пользователей для уведомлений.

### `audit_log`

Журнал админ-действий (`action`, `target`, `admin_ip`).

### `rate_limits`

Per-user и глобальные лимиты запросов.

## Миграции

Применяются автоматически при старте FastAPI (`run_migrations()`).

```bash
ls app/db/migrations/
# 001_init.sql … 011_history_user_cascade.sql
```

## Docker volume

```yaml
- ./app/data:/app/app/data
```

## Безопасность

API-ключи в логах маскируются (`****abcd` — последние 4 символа).
