# API — Аутентификация

## POST /auth/register

Регистрация пользователя.

```bash
curl -X POST https://ваш-домен/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "securepass123",
    "password_confirm": "securepass123"
  }'
```

## POST /auth/verify

Подтверждение email.

```bash
curl -X POST https://ваш-домен/auth/verify \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "token": "..."}'
```

## POST /auth/login

```bash
curl -X POST https://ваш-домен/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "securepass123"}'
```

**Ответ:**

```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "user_id": "uuid",
  "email": "user@example.com",
  "is_verified": true
}
```

## POST /auth/request-reset-password

## POST /auth/reset-password

Сброс пароля по токену из email.

## API-ключи

### POST /api/keys/generate

С JWT (первый ключ) или с `X-API-Key` (дополнительный):

```bash
curl -X POST https://ваш-домен/api/keys/generate \
  -H "Authorization: Bearer eyJ..." \
  -H "Content-Type: application/json" \
  -d '{"name": "Production"}'
```

### GET /api/keys

Список ключей (маскированные префиксы).

### DELETE /api/keys/{key_id}

Отозвать ключ. Нельзя отозвать последний активный.

### POST /api/keys/{key_id}/rotate

Ротация: новый ключ, старый деактивирован.

### PUT /api/keys/{key_id}/rename

Переименовать ключ.

## Переменные окружения

| Переменная | Описание |
|------------|----------|
| `JWT_SECRET_KEY` | Секрет JWT |
| `JWT_EXPIRE_MINUTES` | 15 |
| `EMAIL_FROM` | Отправитель писем |
| `FRONTEND_URL` | База SPA для ссылок |

## Локально без ключей

```bash
DISABLE_AUTH=true   # только dev!
```
