# Agents

Report pipeline specialized agents, each with its own log file.

## Chain

```
context_loader → parser → analyst → visualizer → formatter → sender
```

## Agents

| Agent | File | Role |
|-------|------|------|
| `voice_orchestrator` | `app/voice/orchestrator.py` | Voice → intent → pipeline |
| `agent_context_loader` | `app/agents/context_loader.py` | User preferences |
| `agent_parser` | `app/agents/parser.py` | CSV/Excel/Sheets → DataFrame |
| `agent_analyst` | `app/agents/analyst.py` | Metrics, insights |
| `agent_visualizer` | `app/agents/visualizer.py` | matplotlib charts |
| `agent_formatter` | `app/agents/formatter.py` | PDF/Excel/PPTX/Notion/Slides |
| `agent_sender` | `app/agents/sender.py` | SMTP email |

## Self-healing

`@with_self_healing` decorator wraps agents. On error — ChromaDB lookup and automatic retry.

See [Self-healing](self-healing.md)
