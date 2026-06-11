#!/usr/bin/env bash
# Check ports 80/443 before starting Traefik (production).
set -euo pipefail

port_in_use() {
  local port="$1"
  if command -v ss >/dev/null 2>&1; then
    ss -tlnH 2>/dev/null | awk -v p=":${port}" '$4 ~ p"$" {found=1} END {exit !found}'
    return $?
  fi
  if command -v netstat >/dev/null 2>&1; then
    netstat -tln 2>/dev/null | grep -q ":${port} "
    return $?
  fi
  return 1
}

show_port_usage() {
  local port="$1"
  echo "==> Port ${port} is already in use:"
  if command -v ss >/dev/null 2>&1; then
    ss -tlnp 2>/dev/null | grep ":${port} " || true
  fi
  echo ""
  echo "Docker containers publishing 80/443:"
  docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' 2>/dev/null \
    | grep -E '0\.0\.0\.0:80|0\.0\.0\.0:443|\[::\]:80|\[::\]:443' || echo "(none)"
}

main() {
  local failed=0

  for port in 80 443; do
    if port_in_use "$port"; then
      show_port_usage "$port"
      failed=1
    fi
  done

  if [[ "$failed" -ne 0 ]]; then
    echo ""
    echo "Traefik needs ports 80 and 443. Choose one:" >&2
    echo "  A) Free the ports on VPS (common: nginx/apache or old container):" >&2
    echo "       sudo systemctl stop nginx" >&2
    echo "       docker ps   # docker stop <container>" >&2
    echo "  B) Keep host nginx — in .env set:" >&2
    echo "       TRAEFIK_ENABLED=false" >&2
    echo "     then configure nginx → 127.0.0.1:8000 (see docs/nginx-host.example.conf)" >&2
    exit 1
  fi

  echo "==> Ports 80/443 are free"
}

main "$@"
