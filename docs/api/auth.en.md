# API — Authentication

## POST /auth/register

```bash
curl -X POST https://your-domain/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "securepass123", "password_confirm": "securepass123"}'
```

## POST /auth/login

Returns JWT (15 min) for first API key creation.

## API keys

### POST /api/keys/generate

With JWT (first key) or `X-API-Key` (additional keys).

### GET /api/keys

List keys (masked prefixes).

### DELETE /api/keys/{key_id}

Revoke key.

### POST /api/keys/{key_id}/rotate

Rotate key.

## Dev only

```bash
DISABLE_AUTH=true
```
