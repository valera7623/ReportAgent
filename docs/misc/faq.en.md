# FAQ

## General

### What is ReportAgent?

Micro-SaaS for automated analytical reports with charts from CSV, Excel, and Google Sheets.

### Is OpenAI required?

For **voice input** — yes. For standard file reports — no.

## Registration

### Verification email not received

Check `SMTP_*` in `.env` and spam folder.

### Lost API key

Full key cannot be recovered. Create a new one or rotate.

## Reports

### Slow generation

Usually 5–30 seconds. Check Celery worker logs.

### Google Sheets not readable

Sheet must be **public** (Anyone with the link → Viewer).

## Voice

### Whisper 401

For ProxyAPI.ru set `OPENAI_BASE_URL=https://api.proxyapi.ru/openai/v1`.

## Documentation

- `/help/` — MkDocs guides
- `/docs` — Swagger API

Build: `./scripts/build-docs.sh`
