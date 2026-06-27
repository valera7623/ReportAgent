# Агенты

Pipeline генерации отчёта состоит из специализированных агентов. Каждый логирует в отдельный файл.

## Цепочка

```mermaid
flowchart LR
    CL[context_loader] --> P[parser]
    P --> A[analyst]
    A --> V[visualizer]
    V --> F[formatter]
    F --> S[sender]
```

## Агенты

| Агент | Файл | Назначение |
|-------|------|------------|
| `voice_orchestrator` | `app/voice/orchestrator.py` | Голос → intent → pipeline |
| `agent_context_loader` | `app/agents/context_loader.py` | Preferences пользователя |
| `agent_parser` | `app/agents/parser.py` | CSV/Excel/Sheets → DataFrame |
| `agent_analyst` | `app/agents/analyst.py` | Метрики, инсайты |
| `agent_visualizer` | `app/agents/visualizer.py` | Графики matplotlib |
| `agent_formatter` | `app/agents/formatter.py` | PDF/Excel/PPTX/Notion/Slides |
| `agent_sender` | `app/agents/sender.py` | Email SMTP |

## Логи

| Агент | Лог |
|-------|-----|
| parser | `logs/log_parser.log` |
| analyst | `logs/log_analyst.log` |
| visualizer | `logs/log_visualizer.log` |
| formatter | `logs/log_formatter.log` |
| sender | `logs/log_sender.log` |
| voice | `logs/log_voice.log` |

## Self-healing

Декоратор `@with_self_healing` оборачивает агентов. При ошибке — поиск в ChromaDB и автоматический retry.

См. [Self-healing](self-healing.md)

## Метрики

Prometheus: `agent_duration_seconds`, `agent_errors_total`, `report_generation_duration_seconds`
