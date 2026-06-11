#!/usr/bin/env bash
# Pull third-party images with retries (Docker Hub is often slow/unreachable from WSL/VPS).
set -euo pipefail

PULL_RETRIES="${PULL_RETRIES:-5}"
PULL_RETRY_DELAY="${PULL_RETRY_DELAY:-20}"

TRAEFIK_IMAGE="${TRAEFIK_IMAGE:-traefik:v3.0}"
REDIS_IMAGE="${REDIS_IMAGE:-redis:7-alpine}"

pull_one() {
  local image="$1"
  local attempt=1

  while [[ "$attempt" -le "$PULL_RETRIES" ]]; do
    echo "==> Pulling ${image} (attempt ${attempt}/${PULL_RETRIES})"
    if docker pull "$image"; then
      echo "==> OK: ${image}"
      return 0
    fi
    echo "WARNING: pull failed for ${image}"
    if [[ "$attempt" -lt "$PULL_RETRIES" ]]; then
      echo "       Retrying in ${PULL_RETRY_DELAY}s..."
      sleep "$PULL_RETRY_DELAY"
    fi
    attempt=$((attempt + 1))
  done

  echo "ERROR: could not pull ${image} after ${PULL_RETRIES} attempts." >&2
  return 1
}

main() {
  local failed=0

  pull_one "$REDIS_IMAGE" || failed=1
  pull_one "$TRAEFIK_IMAGE" || failed=1

  if [[ "$failed" -ne 0 ]]; then
    echo "" >&2
    echo "Docker Hub pull failed (connection timeout is common on WSL/restricted networks)." >&2
    echo "" >&2
    echo "Try one of:" >&2
    echo "  1. Local dev without Traefik:  ./deploy-dev.sh" >&2
    echo "  2. Redis mirror in .env:       REDIS_IMAGE=public.ecr.aws/docker/library/redis:7-alpine" >&2
    echo "  3. Docker registry mirror in /etc/docker/daemon.json (see README)." >&2
    echo "  4. Retry later or use VPN, then: ./deploy.sh" >&2
    return 1
  fi
}

main "$@"
