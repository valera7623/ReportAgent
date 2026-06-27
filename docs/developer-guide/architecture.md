# Архитектура

## Обзор

ReportAgent — FastAPI-приложение с фоновым pipeline на Celery, Redis, SQLite и статическим фронтендом (Vanilla JS).

```mermaid
flowchart TB
    subgraph Client
        Browser[Browser / API client]
    end

    subgraph Docker
        API[fastapi :8000]
        Worker[celery_worker]
        Beat[celery_beat]
        Redis[(redis:6379)]
        Prom[prometheus]
        Graf[grafana]
    end

    subgraph Data
        DB[(SQLite users.db)]
        Storage[storage/ PDFs charts]
        Chroma[chroma_data/]
    end

    subgraph External
        OpenAI[OpenAI Whisper GPT]
        SMTP[SMTP]
        Stripe[Stripe YooKassa]
    end

    Browser -->|HTTP| API
    API --> DB
    API --> Redis
    Worker --> Redis
    Worker --> DB
    Worker --> Storage
    Worker --> Chroma
    Worker --> OpenAI
    Worker --> SMTP
    API --> Stripe
    Prom --> API
    Graf --> Prom
```

## Слои приложения

| Слой | Каталог | Ответственность |
|------|---------|-----------------|
| Routers | `app/routers/` | HTTP API |
| Agents | `app/agents/` | Pipeline отчётов |
| Voice | `app/voice/` | Whisper + intent |
| Middleware | `app/middleware/` | Auth, rate limit, metrics |
| Tasks | `app/tasks.py` | Celery orchestration |
| DB | `app/db/` | SQLite, миграции |
| Admin | `app/admin/` | Admin API helpers |
| Self-healing | `app/self_healing/` | ChromaDB RAG |
| Frontend | `frontend/` | SPA (hash routes) |

## Pipeline отчёта

```
context_loader → parser → analyst → visualizer → formatter → sender
```

Голосовой путь: `voice/orchestrator` → тот же pipeline.

## Аутентификация

- **JWT** (15 мин) — регистрация, создание первого ключа
- **X-API-Key** — все защищённые эндпоинты
- **X-Admin-Key** — `/admin/*`

## Документация

MkDocs Material → `site/` → монтируется на `/help/` в FastAPI.

## CI/CD

GitHub Actions → SSH VPS → `./deploy.sh`

## Связанные документы

- [Схема БД](database-schema.md)
- [Агенты](agents.md)
- [Self-healing](self-healing.md)
