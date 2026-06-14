#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

NETWORK_NAME="traefik_network"
COMPOSE_FILE="docker-compose.prod.yml"

echo "==> ReportAgent production deploy"

if ! docker network inspect "$NETWORK_NAME" >/dev/null 2>&1; then
  echo "==> Creating Docker network: $NETWORK_NAME"
  docker network create "$NETWORK_NAME"
else
  echo "==> Docker network $NETWORK_NAME already exists"
fi

if [[ -f .env ]]; then
  echo "==> Loading environment from .env"
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
else
  echo "WARNING: .env not found. Copy .env.example to .env and configure it."
fi

DOMAIN="${DOMAIN:-your-domain}"
GRAFANA_DOMAIN="${GRAFANA_DOMAIN:-grafana.${DOMAIN}}"
export GRAFANA_DOMAIN

if [[ -n "${EXTERNAL_NGINX_NETWORK:-}" && "$DOMAIN" == "${DOMAIN%%.*}" ]]; then
  echo "WARNING: DOMAIN=$DOMAIN has no subdomain; use reportagent.your-domain for ReportAgent API."
fi
if [[ "$DOMAIN" == "fileguardian.info" ]]; then
  echo "WARNING: DOMAIN=fileguardian.info is the SMDG root site."
  echo "         Set DOMAIN=reportagent.fileguardian.info in .env for ReportAgent API and /metrics."
fi

if [[ -z "${GRAFANA_ADMIN_PASSWORD:-}" ]]; then
  GRAFANA_ADMIN_PASSWORD="$(openssl rand -base64 18 | tr -dc 'a-zA-Z0-9' | head -c 24)"
  export GRAFANA_ADMIN_PASSWORD
  echo "==> Generated GRAFANA_ADMIN_PASSWORD (add to .env): ${GRAFANA_ADMIN_PASSWORD}"
fi

if [[ -z "${ADMIN_API_KEY:-}" || "${ADMIN_API_KEY}" == "change-me-generate-on-deploy" ]]; then
  ADMIN_API_KEY="$(openssl rand -hex 24)"
  export ADMIN_API_KEY
  echo "==> Generated ADMIN_API_KEY for self-healing admin API (add to .env): ${ADMIN_API_KEY}"
fi

GRAFANA_ADMIN_USER="${GRAFANA_ADMIN_USER:-admin}"
if command -v htpasswd >/dev/null 2>&1; then
  export GRAFANA_BASICAUTH_USERS
  GRAFANA_BASICAUTH_USERS="$(htpasswd -nbB "${GRAFANA_ADMIN_USER}" "${GRAFANA_ADMIN_PASSWORD}" | sed -e 's/\$/$$/g')"
elif docker info >/dev/null 2>&1; then
  export GRAFANA_BASICAUTH_USERS
  GRAFANA_BASICAUTH_USERS="$(docker run --rm httpd:2.4-alpine htpasswd -nbB "${GRAFANA_ADMIN_USER}" "${GRAFANA_ADMIN_PASSWORD}" | sed -e 's/\$/$$/g')"
else
  echo "WARNING: htpasswd not found; Grafana Traefik basic auth uses compose default."
fi

TRAEFIK_ENABLED="${TRAEFIK_ENABLED:-true}"
OBSERVABILITY_HOST_METRICS="${OBSERVABILITY_HOST_METRICS:-true}"
COMPOSE_ARGS=(-f "$COMPOSE_FILE")
COMPOSE_PROFILE_ARGS=()

if [[ "$TRAEFIK_ENABLED" == "true" ]]; then
  echo "==> Mode: Traefik (ports 80/443)"
  COMPOSE_PROFILE_ARGS+=(--profile traefik)
  if [[ "${SKIP_PORT_CHECK:-0}" != "1" ]]; then
    ./scripts/preflight-prod.sh
  fi
else
  if [[ -n "${EXTERNAL_NGINX_NETWORK:-}" ]]; then
    echo "==> Mode: existing Docker nginx (network: ${EXTERNAL_NGINX_NETWORK})"
    COMPOSE_ARGS+=(-f docker-compose.prod.external-nginx.yml)
  else
    echo "==> Mode: host nginx (Traefik disabled, FastAPI on 127.0.0.1:8000)"
    COMPOSE_ARGS+=(-f docker-compose.prod.host-nginx.yml)
  fi
fi

if [[ "$OBSERVABILITY_HOST_METRICS" == "true" ]]; then
  echo "==> Observability: enabling node_exporter + cadvisor (set OBSERVABILITY_HOST_METRICS=false on low-RAM VPS)"
  COMPOSE_PROFILE_ARGS+=(--profile observability-host)
fi

mkdir -p \
  app/data storage/pdfs storage/uploads storage/formatted logs traefik/acme \
  chroma_data \
  prometheus alertmanager \
  grafana/provisioning/datasources grafana/provisioning/dashboards grafana/dashboards

chmod 777 chroma_data 2>/dev/null || true

chmod +x scripts/healthcheck_celery.sh scripts/healthcheck_celery_beat.sh scripts/pull-images.sh scripts/preflight-prod.sh \
  scripts/setup-grafana.sh scripts/render-alertmanager.sh scripts/test_alerts.py \
  scripts/diagnose_observability.sh scripts/check-nginx-grafana.sh 2>/dev/null || true

echo "==> Rendering Alertmanager config"
./scripts/render-alertmanager.sh

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "WARNING: ffmpeg not found on host (optional; required inside Docker image for voice/pydub)."
fi
touch traefik/acme/acme.json
chmod 600 traefik/acme/acme.json 2>/dev/null || true

echo "==> Preparing Prometheus data volume permissions"
docker volume create reportagent_prometheus_data 2>/dev/null || docker volume create prometheus_data 2>/dev/null || true
PROM_VOL_DIR="$(docker volume inspect reportagent_prometheus_data -f '{{.Mountpoint}}' 2>/dev/null || docker volume inspect prometheus_data -f '{{.Mountpoint}}' 2>/dev/null || echo "")"
if [[ -n "$PROM_VOL_DIR" && -d "$PROM_VOL_DIR" ]]; then
  sudo chmod 777 "$PROM_VOL_DIR" 2>/dev/null || chmod 777 "$PROM_VOL_DIR" 2>/dev/null || true
fi

echo "==> Building app image"
docker compose "${COMPOSE_ARGS[@]}" build

if [[ "${SKIP_PULL:-0}" != "1" ]]; then
  if [[ "$TRAEFIK_ENABLED" == "true" ]]; then
    echo "==> Pulling external images (Traefik, Redis, observability)"
    if ! ./scripts/pull-images.sh; then
      echo ""
      echo "Production deploy aborted: could not pull external images."
      echo "For local testing use: ./deploy-dev.sh"
      exit 1
    fi
  else
    echo "==> Pulling Redis + observability images (Traefik skipped)"
    PULL_RETRIES="${PULL_RETRIES:-5}" REDIS_IMAGE="${REDIS_IMAGE:-redis:7-alpine}" \
      bash -c '
        img="${REDIS_IMAGE:-redis:7-alpine}"
        for i in $(seq 1 "${PULL_RETRIES:-5}"); do
          docker pull "$img" && exit 0
          sleep "${PULL_RETRY_DELAY:-20}"
        done
        exit 1
      ' || {
        echo "Redis pull failed. Set REDIS_IMAGE mirror in .env or SKIP_PULL=1"
        exit 1
      }
    OBSERVABILITY_HOST_METRICS="${OBSERVABILITY_HOST_METRICS:-true}" ./scripts/pull-images.sh observability-only || true
  fi
else
  echo "==> SKIP_PULL=1 — skipping docker pull"
fi

echo "==> Stopping existing stack"
docker compose "${COMPOSE_ARGS[@]}" "${COMPOSE_PROFILE_ARGS[@]}" down --remove-orphans 2>/dev/null || \
  docker compose "${COMPOSE_ARGS[@]}" down --remove-orphans

echo "==> Starting stack"
docker compose "${COMPOSE_ARGS[@]}" "${COMPOSE_PROFILE_ARGS[@]}" up -d --pull never

echo "==> Pruning dangling images"
docker system prune -f

echo ""
echo "==> Container status"
docker compose "${COMPOSE_ARGS[@]}" "${COMPOSE_PROFILE_ARGS[@]}" ps

echo ""
if [[ "$TRAEFIK_ENABLED" == "true" ]]; then
  echo "Deploy complete."
  echo "  API docs:    https://${DOMAIN}/docs"
  echo "  Metrics:     https://${DOMAIN}/metrics"
  echo "  Grafana:     https://${GRAFANA_DOMAIN}/d/ReportAgent-Main/reportagent-main"
  echo "  Grafana login: ${GRAFANA_ADMIN_USER} / (see GRAFANA_ADMIN_PASSWORD in .env or log above)"
elif [[ -n "${EXTERNAL_NGINX_NETWORK:-}" ]]; then
  echo "Deploy complete. Add nginx proxy → http://reportagent_fastapi:8000"
  echo "See docs/nginx-docker-existing.example.conf"
else
  echo "Deploy complete. Configure nginx → http://127.0.0.1:8000 (see docs/nginx-host.example.conf)"
  echo "Local check: curl http://127.0.0.1:8000/health"
fi
