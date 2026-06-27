# Self-healing RAG

Агенты автоматически учатся на ошибках через ChromaDB и локальные эмбеддинги.

## Как это работает

1. Агент падает → `@with_self_healing` извлекает сигнатуру ошибки
2. ChromaDB ищет похожие записи (`all-MiniLM-L6-v2`, без OpenAI)
3. Если найдено решение с `was_successful=true` → `FixExecutor` применяет фикс и повторяет
4. Успех → `success_count++`, алерт в Telegram
5. Celery Beat (`learn_from_failures`) — анализ неудач через GPT-4o-mini каждый час

## Конфигурация

```bash
SELF_HEALING_ENABLED=true
CHROMA_PERSIST_DIR=./chroma_data
SIMILARITY_THRESHOLD=0.75
MAX_RETRY_ATTEMPTS=2
```

При первом запуске загружаются **seed-фиксы** из `app/self_healing/seed_fixes.json`.

## Admin API

```bash
curl https://ваш-домен/admin/self-healing/stats -H "X-Admin-Key: $ADMIN_KEY"
curl -X POST https://ваш-домен/admin/self-healing/seed-fixes?overwrite=true \
  -H "X-Admin-Key: $ADMIN_KEY"
```

## Примеры seed-фиксов

| Ошибка | Решение |
|--------|---------|
| `ParserError: tokenizing` | `sep=';'`, `engine='python'` |
| `KeyError: 'sales'` | fuzzy matching столбца |
| `matplotlib: no display` | `matplotlib.use('Agg')` |
| `UnicodeDecodeError` | `encoding='latin-1'` |

## Безопасность

- `solution_code` — только JSON action specs, **eval запрещён**
- Self-healing отключается при RAM < `SELF_HEALING_MIN_RAM_MB`

## Метрики

- `self_healing_attempts_total{agent_name,success}`
- `knowledge_base_size`

## Тест

```bash
python3 scripts/test_self_healing.py --base-url http://localhost:8000
```
