# Monitoring

ReportAgent includes Prometheus, Grafana, and Telegram alerts via Alertmanager.

## Health endpoints

```bash
curl -s https://your-domain/health
curl -s https://your-domain/metrics | head -40
```

## Grafana

Dashboard: `https://grafana.domain/d/ReportAgent-Main/reportagent-main`

## Admin health API

```bash
curl https://your-domain/admin/health/all -H "X-Admin-Key: $ADMIN_API_KEY"
```

## Key metrics

| Metric | Purpose |
|--------|---------|
| `report_requests_total` | Request rate |
| `agent_duration_seconds` | Agent timing |
| `celery_queue_length` | Celery queue depth |
| `self_healing_attempts_total` | Self-healing |

## Diagnostics

```bash
./scripts/diagnose_observability.sh
```

Low-RAM VPS: `OBSERVABILITY_HOST_METRICS=false`
