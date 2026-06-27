# Self-healing RAG

Agents learn from errors via ChromaDB and local embeddings.

## How it works

1. Agent fails → `@with_self_healing` extracts error signature
2. ChromaDB searches similar records (`all-MiniLM-L6-v2`)
3. If a successful fix exists → `FixExecutor` applies and retries
4. Celery Beat (`learn_from_failures`) analyzes failures hourly via GPT-4o-mini

## Configuration

```bash
SELF_HEALING_ENABLED=true
CHROMA_PERSIST_DIR=./chroma_data
```

Seed fixes: `app/self_healing/seed_fixes.json`

## Admin API

```bash
curl https://your-domain/admin/self-healing/stats -H "X-Admin-Key: $ADMIN_KEY"
```

## Test

```bash
python3 scripts/test_self_healing.py
```
