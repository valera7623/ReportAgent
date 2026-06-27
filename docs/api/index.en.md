# API Overview

ReportAgent REST API on FastAPI.

## Base URL

```
https://reportagent.fileguardian.info
```

Local: `http://localhost:8000`

## Interactive docs

| URL | Format |
|-----|--------|
| `/docs` | Swagger UI |
| `/help/` | MkDocs guides |

## Authentication

```http
X-API-Key: ra_your_key
Authorization: Bearer eyJ...   # JWT for registration flow
X-Admin-Key: your_admin_key    # Admin API
```

## API sections

| Doc | Prefix |
|-----|--------|
| [Auth](auth.md) | `/auth`, `/api/keys` |
| [Reports](reports.md) | `/generate_report`, `/tasks` |
| [Preview](preview.md) | `/api/reports/preview` |
| [Voice](voice.md) | `/voice` |
| [Webhooks](webhooks.md) | `/api/webhooks` |
| [Payments](payments.md) | `/api/payments` |
| [Admin](admin.md) | `/admin` |
