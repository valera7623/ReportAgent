# Architecture

## Overview

ReportAgent is a FastAPI app with a Celery report pipeline, Redis, SQLite, and a Vanilla JS frontend.

## Application layers

| Layer | Directory | Responsibility |
|-------|-----------|----------------|
| Routers | `app/routers/` | HTTP API |
| Agents | `app/agents/` | Report pipeline |
| Voice | `app/voice/` | Whisper + intent |
| Middleware | `app/middleware/` | Auth, rate limit, metrics |
| Tasks | `app/tasks.py` | Celery orchestration |
| DB | `app/db/` | SQLite, migrations |
| Frontend | `frontend/` | SPA (hash routes) |

## Report pipeline

```
context_loader → parser → analyst → visualizer → formatter → sender
```

## Authentication

- **JWT** (15 min) — registration, first API key
- **X-API-Key** — protected endpoints
- **X-Admin-Key** — `/admin/*`

## Documentation

MkDocs Material → `site/` → mounted at `/help/` in FastAPI.

See [Database schema](database-schema.md), [Agents](agents.md), [Self-healing](self-healing.md).
