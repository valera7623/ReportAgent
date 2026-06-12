#!/usr/bin/env bash
# Verify Grafana provisioning and optionally create an API key via Grafana HTTP API.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

GRAFANA_ADMIN_USER="${GRAFANA_ADMIN_USER:-admin}"
GRAFANA_ADMIN_PASSWORD="${GRAFANA_ADMIN_PASSWORD:-}"
GRAFANA_URL="${GRAFANA_URL:-http://localhost:3000}"
DOMAIN="${DOMAIN:-example.com}"
GRAFANA_DOMAIN="${GRAFANA_DOMAIN:-grafana.${DOMAIN}}"

echo "==> ReportAgent Grafana setup"

required=(
  grafana/provisioning/datasources/prometheus.yml
  grafana/provisioning/dashboards/dashboards.yml
  grafana/dashboards/reportagent-dashboard.json
)

for f in "${required[@]}"; do
  if [[ ! -f "$f" ]]; then
    echo "ERROR: missing $f" >&2
    exit 1
  fi
  echo "  OK: $f"
done

echo "==> Dashboard UID: ReportAgent-Main"
echo "==> Public URL (after deploy): https://${GRAFANA_DOMAIN}/d/ReportAgent-Main/reportagent-main"

if [[ -z "$GRAFANA_ADMIN_PASSWORD" ]]; then
  echo "WARNING: GRAFANA_ADMIN_PASSWORD not set in .env — using Grafana container default until changed."
  exit 0
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "curl not found; skipping live API checks."
  exit 0
fi

echo "==> Waiting for Grafana at ${GRAFANA_URL} ..."
for i in $(seq 1 30); do
  if curl -sf "${GRAFANA_URL}/api/health" >/dev/null 2>&1; then
    break
  fi
  sleep 2
  if [[ "$i" -eq 30 ]]; then
    echo "Grafana not reachable at ${GRAFANA_URL}. Start stack first: ./deploy.sh"
    exit 1
  fi
done

echo "==> Checking Prometheus datasource"
curl -sf -u "${GRAFANA_ADMIN_USER}:${GRAFANA_ADMIN_PASSWORD}" \
  "${GRAFANA_URL}/api/datasources/name/Prometheus" | grep -q '"name":"Prometheus"' \
  && echo "  Prometheus datasource: OK" \
  || echo "  WARNING: datasource not found yet (provisioning may need a restart)"

echo "==> Creating read-only API key (optional)"
KEY_NAME="reportagent-provision-$(date +%Y%m%d)"
API_RESPONSE=$(curl -sf -u "${GRAFANA_ADMIN_USER}:${GRAFANA_ADMIN_PASSWORD}" \
  -H "Content-Type: application/json" \
  -X POST "${GRAFANA_URL}/api/auth/keys" \
  -d "{\"name\":\"${KEY_NAME}\",\"role\":\"Viewer\",\"secondsToLive\":86400}" 2>/dev/null || true)

if [[ -n "$API_RESPONSE" ]] && echo "$API_RESPONSE" | grep -q '"key"'; then
  echo "  API key created (24h TTL):"
  echo "$API_RESPONSE" | sed -n 's/.*"key":"\([^"]*\)".*/\1/p'
else
  echo "  Skipped API key creation (may already exist or auth failed)."
fi

echo "==> Grafana setup complete"
