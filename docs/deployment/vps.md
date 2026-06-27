# Деплой на VPS

## Подготовка сервера

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER   # перелогиниться
docker network create traefik_network 2>/dev/null || true
```

## Клонирование и настройка

```bash
git clone https://github.com/valera7623/ReportAgent.git ~/ReportAgent
cd ~/ReportAgent
cp .env.example .env
nano .env
```

Обязательно: `DOMAIN`, `SMTP_*`, `JWT_SECRET_KEY`, `FRONTEND_URL`.

## Режим A — Traefik (порты 80/443)

```bash
TRAEFIK_ENABLED=true
DOMAIN=reportagent.example.com
LETSENCRYPT_EMAIL=admin@example.com
```

```bash
./scripts/build-docs.sh
./deploy.sh
curl https://reportagent.example.com/health
curl https://reportagent.example.com/help/
```

## Режим B — External nginx (SMDG)

```bash
TRAEFIK_ENABLED=false
DOMAIN=reportagent.fileguardian.info
```

API слушает `127.0.0.1:8000` на хосте. Nginx проксирует поддомен → `http://172.17.0.1:8000`.

Пример конфигурации: `docs/smdg-edge-proxy.example.conf`

!!! note
    `curl http://localhost:8000/health` на VPS может не работать снаружи — проверяйте через поддомен или `docker exec`.

## Grafana

```bash
GRAFANA_DOMAIN=grafana.reportagent.fileguardian.info
```

Пример nginx: `docs/nginx-grafana.example.conf`

## Синхронизация с GitHub

```bash
./scripts/sync-pull.sh --deploy
```

## Troubleshooting

### `reportagent_fastapi is unhealthy`

Проверьте `DATABASE_URL=sqlite:///./app/data/users.db` (не PostgreSQL).

### Port 80 already allocated

См. README — варианты A/B/C (Traefik vs shared nginx).

### Docker Hub timeout

```bash
REDIS_IMAGE=public.ecr.aws/docker/library/redis:7-alpine
```
