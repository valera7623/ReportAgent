#!/usr/bin/env bash
# Patch SMDG nginx + compose on VPS for resilient ReportAgent upstreams.
# Usage: ./scripts/sync-smdg-reportagent-nginx.sh [ssh-host]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SSH_HOST="${1:-reportagent-vps}"
REMOTE_SMDG="$(ssh -o ConnectTimeout=15 "$SSH_HOST" 'printf %s "$HOME/SMDG"')"

echo "==> Sync ReportAgent nginx patches to ${SSH_HOST}:${REMOTE_SMDG}"

scp "${REPO_ROOT}/smdg/nginx/upstream-target.conf" \
  "${SSH_HOST}:${REMOTE_SMDG}/nginx/upstream-target.conf"

ssh -o ConnectTimeout=15 "$SSH_HOST" "SMDG_DIR=${REMOTE_SMDG}" bash -s <<'REMOTE'
set -euo pipefail
cd "$SMDG_DIR"

COMPOSE="docker-compose.demo.yml"
NGINX_CONF="nginx-https.conf"

# Dynamic upstream variables (match smdg_upstream pattern).
sed -i 's|proxy_pass http://reportagent_fastapi:8000;|proxy_pass $reportagent_api_upstream;|g' "$NGINX_CONF"
sed -i 's|proxy_pass http://reportagent_grafana:3000;|proxy_pass $reportagent_grafana_upstream;|g' "$NGINX_CONF"

# Persist Docker networks on nginx (reportagent_internal + traefik_network).
if ! grep -q 'reportagent_internal' "$COMPOSE"; then
  sed -i '/- traefik_network$/a\      - reportagent_internal' "$COMPOSE"
fi

if ! grep -q '^  reportagent_internal:' "$COMPOSE"; then
  sed -i '/name: traefik_network$/a\
\
  reportagent_internal:\
    external: true\
    name: reportagent_internal' "$COMPOSE"
fi

echo "==> nginx config test (inside running container if up)"
if docker ps --format '{{.Names}}' | grep -q '^smdg-nginx-1$'; then
  docker exec smdg-nginx-1 nginx -t
  docker compose -f "$COMPOSE" up -d --no-deps --force-recreate nginx
  sleep 5
  docker ps --filter name=smdg-nginx --format '{{.Names}} {{.Status}}'
else
  echo "nginx not running — start with: docker compose -f $COMPOSE up -d nginx"
fi
REMOTE

echo "==> Done"
