# Docker Compose

## Services

| Service | Role |
|---------|------|
| **fastapi** | HTTP API, `/help/`, `/app/` |
| **celery_worker** | Report pipeline |
| **celery_beat** | Scheduled tasks |
| **redis** | Celery broker |
| **prometheus** / **grafana** / **alertmanager** | Observability |

## Files

| File | Purpose |
|------|---------|
| `docker-compose.dev.yml` | Local development |
| `docker-compose.prod.yml` | Production base |
| `docker-compose.prod.traefik.yml` | + Traefik TLS |
| `docker-compose.prod.standalone.yml` | Without Traefik |

## Local dev

```bash
./deploy-dev.sh
```

## Production

```bash
./scripts/build-docs.sh && ./deploy.sh
```
