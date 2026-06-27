# API — обзор

ReportAgent предоставляет REST API на FastAPI.

## Базовый URL

```
https://reportagent.fileguardian.info
```

Локально: `http://localhost:8000`

## Интерактивная документация

| URL | Формат |
|-----|--------|
| `/docs` | Swagger UI (OpenAPI 3) |
| `/redoc` | ReDoc |
| `/openapi.json` | OpenAPI JSON |
| `/help/` | MkDocs (руководства) |

## Аутентификация

### API-ключ (основной)

```http
X-API-Key: ra_ваш_ключ
```

### JWT (регистрация, первый ключ)

```http
Authorization: Bearer eyJ...
```

### Admin API

```http
X-Admin-Key: ваш_admin_ключ
```

## Формат ответов

Ошибки:

```json
{
  "detail": "Сообщение об ошибке"
}
```

| Код | Значение |
|-----|----------|
| 400 | Неверный запрос |
| 401 | Не авторизован |
| 402 | Лимит тарифа |
| 404 | Не найдено |
| 422 | Ошибка валидации |
| 429 | Rate limit |
| 501 | Функция отключена (голос без OpenAI) |

## Публичные эндпоинты (без ключа)

| Method | Path |
|--------|------|
| GET | `/health`, `/metrics` |
| GET | `/docs`, `/redoc`, `/openapi.json` |
| GET | `/help/` |
| POST | `/auth/register`, `/auth/login`, `/auth/verify` |
| POST | `/webhooks/stripe`, `/webhooks/yookassa` |
| GET | `/api/payments/prices` |

## Разделы API

| Документ | Префикс |
|----------|---------|
| [Аутентификация](auth.md) | `/auth`, `/api/keys` |
| [Отчёты](reports.md) | `/generate_report`, `/tasks` |
| [Превью](preview.md) | `/api/reports/preview` |
| [Голос](voice.md) | `/voice` |
| [Webhooks](webhooks.md) | `/api/webhooks` |
| [Платежи](payments.md) | `/api/payments` |
| [Admin](admin.md) | `/admin` |
