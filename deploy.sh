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

mkdir -p storage/pdfs storage/uploads logs traefik/acme
touch traefik/acme/acme.json
chmod 600 traefik/acme/acme.json 2>/dev/null || true
chmod +x scripts/healthcheck_celery.sh scripts/pull-images.sh 2>/dev/null || true

echo "==> Building app image"
docker compose -f "$COMPOSE_FILE" build

if [[ "${SKIP_PULL:-0}" != "1" ]]; then
  echo "==> Pulling external images (Traefik, Redis)"
  if ! ./scripts/pull-images.sh; then
    echo ""
    echo "Production deploy aborted: could not pull Traefik/Redis."
    echo "For local testing use: ./deploy-dev.sh"
    exit 1
  fi
else
  echo "==> SKIP_PULL=1 — skipping docker pull"
fi

echo "==> Stopping existing stack"
docker compose -f "$COMPOSE_FILE" down --remove-orphans

echo "==> Starting stack"
docker compose -f "$COMPOSE_FILE" up -d --pull never

echo "==> Pruning dangling images"
docker system prune -f

echo ""
echo "==> Container status"
docker compose -f "$COMPOSE_FILE" ps

echo ""
echo "Deploy complete. API docs: https://${DOMAIN:-your-domain}/docs"
