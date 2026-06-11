#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

COMPOSE_FILE="docker-compose.dev.yml"

echo "==> ReportAgent DEV deploy (no Traefik, http://localhost:8000)"
echo "==> Redis: local build from cached python:3.12-slim (no docker pull)"

if [[ -f .env ]]; then
  echo "==> Loading environment from .env"
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

mkdir -p storage/pdfs storage/uploads logs
chmod +x scripts/healthcheck_celery.sh scripts/pull-images.sh 2>/dev/null || true

echo "==> Building images (app + redis, no registry pull)"
# Build redis first from local reportagent-app if redis image missing
if ! docker image inspect reportagent-redis:local >/dev/null 2>&1; then
  echo "==> Building reportagent-redis:local from cached app image"
  DOCKER_BUILDKIT=0 docker build --pull=false -t reportagent-redis:local -f docker/redis/Dockerfile .
fi
docker compose -f "$COMPOSE_FILE" build --pull=false

echo "==> Stopping existing dev stack"
docker compose -f "$COMPOSE_FILE" down --remove-orphans 2>/dev/null || true

echo "==> Starting dev stack"
docker compose -f "$COMPOSE_FILE" up -d

echo ""
docker compose -f "$COMPOSE_FILE" ps
echo ""
echo "Dev deploy complete: http://localhost:8000/docs"
