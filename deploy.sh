#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

COMPOSE_FILE="docker-compose.prod.yml"

echo "==> ReportAgent production deploy"

if [[ -f .env ]]; then
  echo "==> Loading environment from .env"
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
else
  echo "WARNING: .env not found. Copy .env.example to .env and configure it."
fi

TRAEFIK_ENABLED="${TRAEFIK_ENABLED:-true}"
OBSERVABILITY_HOST_METRICS="${OBSERVABILITY_HOST_METRICS:-true}"
COMPOSE_ARGS=(-f "$COMPOSE_FILE")
COMPOSE_PROFILE_ARGS=()

if [[ "$TRAEFIK_ENABLED" == "true" ]]; then
  echo "==> Mode: standalone Traefik (ReportAgent owns ports 80/443)"
  COMPOSE_ARGS+=(-f docker-compose.prod.traefik.yml)
  COMPOSE_PROFILE_ARGS+=(--profile traefik)
  if [[ "${SKIP_PORT_CHECK:-0}" != "1" ]]; then
    ./scripts/preflight-prod.sh
  fi
else
  echo "==> Mode: standalone (isolated from SMDG Docker networks)"
  echo "    API on host :8000, Grafana on :3000"
  echo "    Edge proxy (smdg-nginx) → http://172.17.0.1:8000 (see docs/smdg-edge-proxy.example.conf)"
  if [[ -n "${EXTERNAL_NGINX_NETWORK:-}" ]]; then
    echo "WARNING: EXTERNAL_NGINX_NETWORK is deprecated; unset it for SMDG independence."
  fi
  COMPOSE_ARGS+=(-f docker-compose.prod.standalone.yml)
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
  echo "==> Generated ADMIN_API_KEY for admin API (add to .env): ${ADMIN_API_KEY}"
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

if [[ "$OBSERVABILITY_HOST_METRICS" == "true" ]]; then
  echo "==> Observability: enabling node_exporter + cadvisor (set OBSERVABILITY_HOST_METRICS=false on low-RAM VPS)"
  COMPOSE_PROFILE_ARGS+=(--profile observability-host)
fi

mkdir -p \
  app/data storage/pdfs storage/uploads storage/formatted storage/temp logs traefik/acme \
  chroma_data \
  prometheus alertmanager \
  grafana/provisioning/datasources grafana/provisioning/dashboards grafana/dashboards

chmod 777 chroma_data 2>/dev/null || true

chmod +x scripts/healthcheck_celery.sh scripts/healthcheck_celery_beat.sh scripts/pull-images.sh scripts/preflight-prod.sh \
  scripts/setup-grafana.sh scripts/render-alertmanager.sh scripts/test_alerts.py \
  scripts/diagnose_observability.sh scripts/check-nginx-grafana.sh scripts/inject-frontend-seo.sh \
  scripts/generate_seo_assets.py 2>/dev/null || true

echo "==> Rendering Alertmanager config"
./scripts/render-alertmanager.sh

echo "==> Injecting frontend SEO (GA4, Yandex Metrika, SITE_URL from .env)"
./scripts/inject-frontend-seo.sh

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

if [[ -f scripts/build-docs.sh ]]; then
  echo "==> Building documentation site (/help/)"
  chmod +x scripts/build-docs.sh 2>/dev/null || true
  if ! ./scripts/build-docs.sh; then
    if [[ -f site/index.html ]]; then
      echo "WARNING: docs build failed, using existing site/ from git"
    else
      echo "ERROR: docs build failed and site/ is missing — /help/ will be unavailable"
      exit 1
    fi
  fi
else
  echo "WARNING: scripts/build-docs.sh not found — /help/ may be unavailable"
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
    OBSERVABILITY_HOST_METRICS="${OBSERVABILITY_HOST_METRICS:-true}" ./scripts/pull-images.sh observability-only || {
      echo "Observability image pull failed. Set PROMETHEUS_IMAGE/GRAFANA_IMAGE in .env or retry later."
      exit 1
    }
  fi
else
  echo "==> SKIP_PULL=1 — skipping docker pull"
fi

echo "==> Stopping existing stack"
docker compose "${COMPOSE_ARGS[@]}" "${COMPOSE_PROFILE_ARGS[@]}" down --remove-orphans 2>/dev/null || \
  docker compose "${COMPOSE_ARGS[@]}" down --remove-orphans

echo "==> Starting stack"
docker compose "${COMPOSE_ARGS[@]}" "${COMPOSE_PROFILE_ARGS[@]}" up -d --pull missing

echo "==> Pruning dangling images"
docker system prune -f

echo ""
echo "==> Container status"
docker compose "${COMPOSE_ARGS[@]}" "${COMPOSE_PROFILE_ARGS[@]}" ps

echo ""
if [[ "$TRAEFIK_ENABLED" == "true" ]]; then
  echo "Deploy complete."
  echo "  API docs:    https://${DOMAIN}/docs"
  echo "  Help docs:   https://${DOMAIN}/help/"
  echo "  Metrics:     https://${DOMAIN}/metrics"
  echo "  Grafana:     https://${GRAFANA_DOMAIN}/d/ReportAgent-Main/reportagent-main"
  echo "  Grafana login: ${GRAFANA_ADMIN_USER} / (see GRAFANA_ADMIN_PASSWORD in .env or log above)"
elif [[ "$TRAEFIK_ENABLED" != "true" ]]; then
  echo "Deploy complete (standalone, no SMDG Docker network)."
  echo "  API:     http://127.0.0.1:8000/health"
  echo "  Public:  configure smdg-nginx → http://172.17.0.1:8000 (docs/smdg-edge-proxy.example.conf)"
  echo "  Help:    https://${DOMAIN}/help/"
  echo "  Grafana: http://127.0.0.1:3000 (proxy ${GRAFANA_DOMAIN} → :3000)"
fi
