# API — Admin

> **Administrator only.** All actions logged to `audit_log`.

## Authentication

```http
X-Admin-Key: your_admin_key
```

## Endpoints

| Area | Examples |
|------|----------|
| Health | `/admin/health/all` |
| Users | `/admin/users`, block/unblock/delete |
| Celery | `/admin/celery/status`, purge, restart |
| Self-healing | `/admin/self-healing/stats` |
| Logs | `/admin/logs`, stream, download |
| Metrics | `/admin/metrics/summary` |
| Rate limits | `/admin/rate-limits` |

## Test

```bash
ADMIN_API_KEY=your_key python scripts/test_admin_api.py
```
