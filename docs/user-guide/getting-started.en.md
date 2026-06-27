# Getting Started

Guide for ReportAgent users — analysts, managers, and integrators.

## Why ReportAgent

ReportAgent turns tabular data into ready-made reports with charts:

- upload CSV/Excel or provide a Google Sheets URL;
- get PDF, Excel, presentation, or a Notion page;
- configure chart type, theme, and default email;
- automate via API and webhooks.

## Registration

1. Open the web UI: `https://your-domain/app#/register`
2. Enter **email** and **password** (minimum 8 characters).
3. Verify email via the link in the message (`/app#/verify`).
4. Log in at `/app#/login`.
5. Create your **first API key** for API access and integrations.

!!! tip "SMTP required for registration"
    The administrator must configure `SMTP_*` and `FRONTEND_URL` in `.env`, otherwise verification emails will not be sent.

## Sign in

### Email + password (web)

1. `/app#/login` → **Email** tab
2. After login you receive a JWT (15 min) to create an API key

### API key (persistent access)

1. `/app#/login` → **API key** tab
2. Paste your `ra_...` key
3. Send all protected requests with:

```http
X-API-Key: ra_your_key
```

## First API key

After JWT login:

```bash
curl -X POST https://your-domain/api/keys/generate \
  -H "Authorization: Bearer eyJ..." \
  -H "Content-Type: application/json" \
  -d '{"name": "Default"}'
```

!!! warning "Key shown once"
    Save the full key immediately. Only the prefix (`ra_abc12`) is visible in the key list.

## Web interface

After login:

| Section | URL | Purpose |
|---------|-----|---------|
| **Dashboard** | `/app#/dashboard` | Stats, new report |
| **Reports** | `/app#/reports` | Generation history |
| **Keys** | `/app#/keys` | API key management |
| **Preferences** | `/app#/preferences` | Charts, theme, format |
| **Webhooks** | `/app#/webhooks` | Notification URLs |
| **Pricing** | `/app#/pricing` | Subscription |

## Quick test

```bash
TASK_ID=$(curl -s -X POST https://your-domain/generate_report \
  -H "X-API-Key: $API_KEY" \
  -F "file=@samples/sample_sales.csv" | jq -r .task_id)

curl -OJ -H "X-API-Key: $API_KEY" \
  "https://your-domain/tasks/${TASK_ID}/pdf"
```

## Next steps

- [Creating reports](reports.md)
- [Preview before send](preview.md)
- [Auth API](../api/auth.md)
