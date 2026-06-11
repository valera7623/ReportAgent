#!/usr/bin/env bash
# Executed on the VPS by GitHub Actions (or manually after SSH).
set -euo pipefail

DEPLOY_PATH="${DEPLOY_PATH:-${HOME}/ReportAgent}"
DEPLOY_BRANCH="${DEPLOY_BRANCH:-main}"
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
  echo "WARNING: fastapi container is not healthy yet"
  docker compose -f docker-compose.prod.yml logs --tail=30 fastapi || true
fi
