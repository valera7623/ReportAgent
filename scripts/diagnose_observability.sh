#!/usr/bin/env bash
# Quick observability diagnostics on VPS (external nginx or Traefik mode).
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

DOMAIN="${DOMAIN:-reportagent.fileguardian.info}"
GRAFANA_DOMAIN="${GRAFANA_DOMAIN:-grafana.${DOMAIN}}"

echo "==> ReportAgent observability diagnostics"
echo "    DOMAIN=$DOMAIN"
echo "    GRAFANA_DOMAIN=$GRAFANA_DOMAIN"
echo ""

check_container() {
  local name="$1"
  if docker ps --format '{{.Names}}' | grep -qx "$name"; then
    echo "  OK   container running: $name"
  else
    echo "  FAIL container missing: $name"
  fi
}

for c in reportagent_fastapi reportagent_prometheus reportagent_grafana reportagent_alertmanager reportagent_celery_beat; do
  check_container "$c"
done

echo ""
echo "==> FastAPI /metrics (public)"
if curl -sf --max-time 10 "https://${DOMAIN}/metrics" | grep -q report_requests_total; then
  echo "  OK   https://${DOMAIN}/metrics"
else
  echo "  FAIL https://${DOMAIN}/metrics"
fi

echo ""
echo "==> Prometheus → FastAPI (Docker DNS, use container name)"
if docker exec reportagent_prometheus wget -qO- http://reportagent_fastapi:8000/metrics 2>/dev/null | grep -q report_requests_total; then
  echo "  OK   reportagent_prometheus → reportagent_fastapi:8000"
else
  echo "  FAIL reportagent_prometheus cannot reach reportagent_fastapi:8000"
  echo "       Try: docker network inspect \$(docker inspect reportagent_prometheus --format '{{range \$k,\$v := .NetworkSettings.Networks}}{{\$k}}{{end}}')"
fi

echo ""
echo "==> Grafana → Prometheus (internal)"
if docker exec reportagent_grafana wget -qO- http://reportagent_prometheus:9090/-/healthy 2>/dev/null | grep -q OK; then
  echo "  OK   reportagent_grafana → reportagent_prometheus:9090"
else
  echo "  FAIL grafana cannot reach prometheus"
fi

echo ""
echo "==> Grafana health (internal)"
if docker exec reportagent_grafana wget -qO- http://localhost:3000/api/health 2>/dev/null | grep -q ok; then
  echo "  OK   Grafana API healthy inside container"
else
  echo "  FAIL Grafana API inside container"
fi

echo ""
echo "==> Grafana public URL (DNS + nginx required)"
if curl -sf --max-time 10 -o /dev/null "https://${GRAFANA_DOMAIN}/api/health" 2>/dev/null; then
  echo "  OK   https://${GRAFANA_DOMAIN}"
elif curl -sf --max-time 10 -o /dev/null "http://${GRAFANA_DOMAIN}/api/health" 2>/dev/null; then
  echo "  OK   http://${GRAFANA_DOMAIN} (no TLS yet)"
else
  echo "  FAIL https://${GRAFANA_DOMAIN} not reachable"
  echo "       1) Add DNS A-record for ${GRAFANA_DOMAIN}"
  echo "       2) Add nginx proxy → reportagent_grafana:3000 (docs/nginx-grafana.example.conf)"
  echo "       3) ./deploy.sh after EXTERNAL_NGINX_NETWORK is set"
  echo "       Or SSH tunnel: ssh -L 3000:localhost:3000 user@vps then browse http://localhost:3000"
  echo "       (on VPS: docker exec reportagent_grafana wget -qO- http://localhost:3000/api/health)"
fi

echo ""
echo "==> Prometheus targets (if UI reachable via tunnel)"
echo "    docker exec reportagent_prometheus wget -qO- http://localhost:9090/api/v1/targets"
