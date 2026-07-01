#!/usr/bin/env bash
# Append ReportAgent server blocks to SMDG nginx if missing, then reload nginx.
# Usage:
#   ./scripts/install-reportagent-nginx-block.sh              # local SMDG path
#   ./scripts/install-reportagent-nginx-block.sh reportagent-vps
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
MARKER="# --- ReportAgent edge proxy (managed) ---"
SNIPPET="${REPO_ROOT}/smdg/nginx/reportagent-server.conf"
SSH_HOST="${1:-}"

if [[ -n "$SSH_HOST" ]]; then
  echo "==> Installing ReportAgent nginx block on ${SSH_HOST}"
  scp "$SNIPPET" "${SSH_HOST}:~/reportagent-server.conf"
  ssh "$SSH_HOST" "MARKER=$(printf %q "$MARKER")" bash -s <<'REMOTE'
set -euo pipefail
SMDG_DIR="${HOME}/SMDG"
NGINX_CONF="${SMDG_DIR}/nginx-https.conf"
if grep -qF "$MARKER" "$NGINX_CONF" 2>/dev/null; then
  echo "ReportAgent nginx block already present in ${NGINX_CONF}"
else
  echo "==> Appending ReportAgent server blocks to ${NGINX_CONF}"
  cat ~/reportagent-server.conf >> "$NGINX_CONF"
  rm -f ~/reportagent-server.conf
fi
if docker ps --format '{{.Names}}' | grep -q '^smdg-nginx-1$'; then
  docker exec smdg-nginx-1 nginx -t
  docker exec smdg-nginx-1 nginx -s reload
  echo "==> nginx reloaded"
else
  echo "WARNING: smdg-nginx-1 not running — start SMDG nginx and reload manually"
fi
REMOTE
  exit 0
fi

SMDG_DIR="${SMDG_DIR:-${HOME}/SMDG}"
NGINX_CONF="${SMDG_DIR}/nginx-https.conf"
if [[ ! -f "$NGINX_CONF" ]]; then
  echo "ERROR: ${NGINX_CONF} not found. Set SMDG_DIR or pass SSH host." >&2
  exit 1
fi
if grep -qF "$MARKER" "$NGINX_CONF"; then
  echo "ReportAgent nginx block already present"
  exit 0
fi
cat "$SNIPPET" >> "$NGINX_CONF"
echo "Appended to ${NGINX_CONF}. Reload nginx: docker exec smdg-nginx-1 nginx -s reload"
