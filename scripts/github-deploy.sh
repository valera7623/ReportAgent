#!/usr/bin/env bash
# Executed on the VPS by GitHub Actions (or manually after SSH).
set -euo pipefail

DEPLOY_PATH="${DEPLOY_PATH:-${HOME}/ReportAgent}"
DEPLOY_BRANCH="${DEPLOY_BRANCH:-master}"
REPO_URL="${REPO_URL:-}"

cd "$DEPLOY_PATH"

if [[ ! -d .git ]]; then
  if [[ -z "$REPO_URL" ]]; then
    echo "ERROR: $DEPLOY_PATH is not a git repo and REPO_URL is not set." >&2
    exit 1
  fi
  echo "==> Cloning repository into $DEPLOY_PATH"
  mkdir -p "$(dirname "$DEPLOY_PATH")"
  git clone --branch "$DEPLOY_BRANCH" "$REPO_URL" "$DEPLOY_PATH"
  cd "$DEPLOY_PATH"
fi

if [[ -n "${GIT_DEPLOY_TOKEN:-}" && -n "${GITHUB_REPOSITORY:-}" ]]; then
  git remote set-url origin "https://x-access-token:${GIT_DEPLOY_TOKEN}@github.com/${GITHUB_REPOSITORY}.git"
fi

echo "==> Updating code (branch: $DEPLOY_BRANCH)"
git fetch --prune origin
git checkout "$DEPLOY_BRANCH"
git reset --hard "origin/$DEPLOY_BRANCH"

chmod +x deploy.sh deploy-dev.sh scripts/*.sh 2>/dev/null || true

if [[ ! -f .env ]]; then
  echo "ERROR: .env not found in $DEPLOY_PATH" >&2
  echo "Create it once on the server: cp .env.example .env && nano .env" >&2
  exit 1
fi

echo "==> Running production deploy"
./deploy.sh

echo "==> Post-deploy container health"
FASTAPI_HEALTH="$(docker inspect --format='{{.State.Health.Status}}' reportagent_fastapi 2>/dev/null || echo "unknown")"
CELERY_HEALTH="$(docker inspect --format='{{.State.Health.Status}}' reportagent_celery_worker 2>/dev/null || echo "unknown")"
REDIS_HEALTH="$(docker inspect --format='{{.State.Health.Status}}' reportagent_redis 2>/dev/null || echo "unknown")"
echo "fastapi=${FASTAPI_HEALTH} celery=${CELERY_HEALTH} redis=${REDIS_HEALTH}"

if [[ "$FASTAPI_HEALTH" != "healthy" ]]; then
  echo "ERROR: reportagent_fastapi is not healthy" >&2
  docker compose -f docker-compose.prod.yml logs --tail=80 fastapi || true
  echo "==> Container inspect" >&2
  docker inspect reportagent_fastapi --format='Status={{.State.Status}} ExitCode={{.State.ExitCode}} Error={{.State.Error}}' 2>/dev/null || true
  echo "Hint: ensure DATABASE_URL in .env is SQLite or remove it (compose sets sqlite:////app/app/data/users.db)" >&2
  exit 1
fi

echo "==> API health (inside container)"
docker exec reportagent_fastapi curl --fail --silent --max-time 10 http://localhost:8000/health
echo ""

# shellcheck disable=SC1091
source .env 2>/dev/null || true
if [[ -n "${EXTERNAL_NGINX_NETWORK:-}" ]]; then
  NGINX_CONTAINER="${NGINX_CONTAINER:-smdg-nginx-1}"
  if docker ps --format '{{.Names}}' | grep -qx "$NGINX_CONTAINER"; then
    echo "==> API health via Docker nginx ($NGINX_CONTAINER)"
    if docker exec "$NGINX_CONTAINER" curl --fail --silent --max-time 10 http://reportagent_fastapi:8000/health; then
      echo ""
    else
      echo "WARNING: $NGINX_CONTAINER cannot reach reportagent_fastapi — add nginx server block (docs/nginx-docker-existing.example.conf)" >&2
    fi
  fi
fi

echo "==> Deploy on VPS: OK"
