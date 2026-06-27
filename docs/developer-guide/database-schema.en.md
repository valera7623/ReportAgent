# Database Schema

ReportAgent uses **SQLite** (`app/data/users.db`). Migrations: `app/db/migrations/*.sql`.

## Main tables

| Table | Purpose |
|-------|---------|
| `users` | Accounts, email, password hash |
| `api_keys` | Multiple SHA-256 hashed keys per user |
| `preferences` | Chart type, theme, default format |
| `history` | Request analytics per user |
| `subscriptions` / `payments` | Stripe and YooKassa billing |
| `webhooks` | User notification URLs |
| `audit_log` | Admin action log |
| `rate_limits` | Global and per-user limits |

Migrations run automatically on FastAPI startup.

Docker volume: `./app/data:/app/app/data`
