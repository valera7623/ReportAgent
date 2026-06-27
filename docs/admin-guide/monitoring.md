# Мониторинг

ReportAgent включает Prometheus, Grafana и Telegram-алерты через Alertmanager.

## Health-эндпоинты

| URL | Назначение |
|-----|------------|
| `GET /health` | Базовая проверка (200 OK) |
| `GET /metrics` | Prometheus exposition |

```bash
curl -s https://ваш-домен/health
curl -s https://ваш-домен/metrics | head -40
```

## Grafana

| URL | Описание |
|-----|----------|
| `https://grafana.домен/d/ReportAgent-Main/reportagent-main` | Главный дашборд |

Grafana защищена Traefik basic auth + логин Grafana.

## Admin API — системное здоровье

```bash
curl https://ваш-домен/admin/health/all -H "X-Admin-Key: $ADMIN_API_KEY"
curl https://ваш-домен/admin/celery/status -H "X-Admin-Key: $ADMIN_API_KEY"
```

## Ключевые метрики

| Метрика | Назначение |
|---------|------------|
| `report_requests_total` | RPS по эндпоинтам |
| `agent_duration_seconds` | Время агентов |
| `celery_queue_length` | Очередь Celery |
| `voice_transcriptions_total` | Whisper успех/фейл |
| `self_healing_attempts_total` | Self-healing |
| `webhook_attempts_total` | Доставка webhooks |

## Алерты (Prometheus)

Файл `prometheus/alerts.yml`:

- **HighErrorRate** — 5xx > 5% за 5 мин
- **CeleryQueueBacklog** — очередь > 20
- **AgentLongRunning** — p95 > 30 с
- **HighVoiceFailureRate** — ошибки голоса > 20%
- **SelfHealingLowSuccessRate** — success rate < 50%

## Telegram-бот

1. Создайте бота через [@BotFather](https://t.me/BotFather)
2. Добавьте `TELEGRAM_BOT_TOKEN` и `TELEGRAM_CHAT_ID` в `.env`
3. `./deploy.sh` рендерит `alertmanager/alertmanager.yml`

Тест:

```bash
python3 scripts/test_alerts.py --base-url https://ваш-домен --telegram
```

## Docker

```bash
docker compose -f docker-compose.prod.yml ps
docker logs -f reportagent_fastapi --tail=100
docker logs -f reportagent_celery_worker --tail=100
```

## Диагностика

```bash
./scripts/diagnose_observability.sh
./scripts/diagnose_voice.sh recording.wav
```

## VPS с 1–2 GB RAM

```bash
OBSERVABILITY_HOST_METRICS=false
SELF_HEALING_ENABLED=false   # опционально
```
