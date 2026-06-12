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

TRAEFIK_ENABLED="${TRAEFIK_ENABLED:-true}"
COMPOSE_ARGS=(-f "$COMPOSE_FILE")
COMPOSE_UP_ARGS=()

if [[ "$TRAEFIK_ENABLED" == "true" ]]; then
  echo "==> Mode: Traefik (ports 80/443)"
  COMPOSE_UP_ARGS+=(--profile traefik)
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

mkdir -p app/data storage/pdfs storage/uploads logs traefik/acme

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "WARNING: ffmpeg not found on host (optional; required inside Docker image for voice/pydub)."
fi
touch traefik/acme/acme.json
chmod 600 traefik/acme/acme.json 2>/dev/null || true
chmod +x scripts/healthcheck_celery.sh scripts/pull-images.sh scripts/preflight-prod.sh 2>/dev/null || true

echo "==> Building app image"
docker compose "${COMPOSE_ARGS[@]}" build

if [[ "${SKIP_PULL:-0}" != "1" ]]; then
  if [[ "$TRAEFIK_ENABLED" == "true" ]]; then
    echo "==> Pulling external images (Traefik, Redis)"
    if ! ./scripts/pull-images.sh; then
      echo ""
      echo "Production deploy aborted: could not pull Traefik/Redis."
      echo "For local testing use: ./deploy-dev.sh"
      exit 1
    fi
  else
    echo "==> Pulling Redis only (Traefik skipped)"
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
  fi
else
  echo "==> SKIP_PULL=1 — skipping docker pull"
fi

echo "==> Stopping existing stack"
docker compose "${COMPOSE_ARGS[@]}" --profile traefik down --remove-orphans 2>/dev/null || \
  docker compose "${COMPOSE_ARGS[@]}" down --remove-orphans

echo "==> Starting stack"
docker compose "${COMPOSE_ARGS[@]}" up -d --pull never "${COMPOSE_UP_ARGS[@]}"

echo "==> Pruning dangling images"
docker system prune -f

echo ""
echo "==> Container status"
docker compose "${COMPOSE_ARGS[@]}" ps

echo ""
if [[ "$TRAEFIK_ENABLED" == "true" ]]; then
  echo "Deploy complete. API docs: https://${DOMAIN:-your-domain}/docs"
elif [[ -n "${EXTERNAL_NGINX_NETWORK:-}" ]]; then
  echo "Deploy complete. Add nginx proxy → http://reportagent_fastapi:8000"
  echo "See docs/nginx-docker-existing.example.conf"
else
  echo "Deploy complete. Configure nginx → http://127.0.0.1:8000 (see docs/nginx-host.example.conf)"
  echo "Local check: curl http://127.0.0.1:8000/health"
fi
