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

if [[ "$DOMAIN" == "fileguardian.info" || "$DOMAIN" != *"reportagent"* ]]; then
  echo "  WARN DOMAIN=$DOMAIN looks like root domain, not ReportAgent API."
  echo "       Set in .env: DOMAIN=reportagent.fileguardian.info"
  echo "       (fileguardian.info is SMDG; /metrics lives on reportagent subdomain)"
  echo ""
fi

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
echo "==> Shared Docker network (reportagent_internal)"
PROM_NETS="$(docker inspect reportagent_prometheus --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}' 2>/dev/null || true)"
API_NETS="$(docker inspect reportagent_fastapi --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}' 2>/dev/null || true)"
GRAF_NETS="$(docker inspect reportagent_grafana --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}' 2>/dev/null || true)"
echo "    prometheus: $PROM_NETS"
echo "    fastapi:    $API_NETS"
echo "    grafana:    $GRAF_NETS"
if echo "$PROM_NETS $API_NETS" | grep -q reportagent_internal; then
  if echo "$PROM_NETS" | grep -q reportagent_internal && echo "$API_NETS" | grep -q reportagent_internal; then
    echo "  OK   prometheus and fastapi share reportagent_internal"
  else
    echo "  FAIL containers not on same internal network — run: ./deploy.sh"
  fi
else
  echo "  WARN reportagent_internal not found; networks: prometheus=[$PROM_NETS] fastapi=[$API_NETS]"
  echo "       Run ./deploy.sh to recreate stack on named network reportagent_internal"
fi

docker_internal_curl() {
  local from="$1"
  local url="$2"
  docker exec "$from" curl -sf --max-time 10 "$url" 2>/dev/null
}

echo ""
echo "==> FastAPI /metrics (public API domain)"
METRICS_OK=0
for base in "https://${DOMAIN}" "http://${DOMAIN}"; do
  if curl -sf --max-time 10 "${base}/metrics" 2>/dev/null | grep -q report_requests_total; then
    echo "  OK   ${base}/metrics"
    METRICS_OK=1
    break
  fi
done
if [[ "$METRICS_OK" -eq 0 ]]; then
  echo "  FAIL https://${DOMAIN}/metrics"
  if [[ "$DOMAIN" == "fileguardian.info" ]]; then
    echo "       Fix .env: DOMAIN=reportagent.fileguardian.info"
    if curl -sf --max-time 10 "https://reportagent.fileguardian.info/metrics" 2>/dev/null | grep -q report_requests_total; then
      echo "  OK   https://reportagent.fileguardian.info/metrics (works — update DOMAIN in .env)"
    fi
  fi
fi

echo ""
echo "==> Internal connectivity (curl from reportagent_fastapi)"
if docker_internal_curl reportagent_fastapi http://reportagent_fastapi:8000/health | grep -q ok; then
  echo "  OK   fastapi → self :8000"
else
  echo "  FAIL fastapi → self :8000"
fi
if docker_internal_curl reportagent_fastapi http://reportagent_prometheus:9090/-/healthy | grep -q OK; then
  echo "  OK   fastapi → reportagent_prometheus:9090"
else
  echo "  FAIL fastapi → reportagent_prometheus:9090"
fi
if docker_internal_curl reportagent_fastapi http://reportagent_grafana:3000/api/health | grep -q '"database":"ok"'; then
  echo "  OK   fastapi → reportagent_grafana:3000"
else
  echo "  FAIL fastapi → reportagent_grafana:3000"
fi

echo ""
echo "==> Grafana → Prometheus (from grafana container)"
if docker exec reportagent_grafana curl -sf --max-time 10 http://reportagent_prometheus:9090/-/healthy 2>/dev/null | grep -q OK; then
  echo "  OK   grafana → prometheus"
else
  echo "  FAIL grafana → prometheus (check both on reportagent_internal; ./deploy.sh)"
fi

echo ""
echo "==> Grafana health (localhost inside container)"
if docker exec reportagent_grafana curl -sf --max-time 10 http://localhost:3000/api/health 2>/dev/null | grep -q '"database":"ok"'; then
  echo "  OK   Grafana API healthy"
else
  echo "  FAIL Grafana API inside container"
fi

echo ""
echo "==> Grafana public URL"
if curl -sf --max-time 10 -o /dev/null "https://${GRAFANA_DOMAIN}/api/health" 2>/dev/null; then
  echo "  OK   https://${GRAFANA_DOMAIN}"
elif curl -sf --max-time 10 -k -o /dev/null "https://${GRAFANA_DOMAIN}/api/health" 2>/dev/null; then
  echo "  WARN https://${GRAFANA_DOMAIN} — TLS cert hostname mismatch (nginx needs cert for this subdomain)"
  echo "       See docs/nginx-grafana.example.conf (HTTPS section)"
elif curl -sf --max-time 10 -o /dev/null "http://${GRAFANA_DOMAIN}/api/health" 2>/dev/null; then
  echo "  OK   http://${GRAFANA_DOMAIN} (HTTP only — add HTTPS in nginx)"
else
  echo "  FAIL ${GRAFANA_DOMAIN} not reachable"
  echo "       DNS + nginx proxy → reportagent_grafana:3000 (docs/nginx-grafana.example.conf)"
fi

echo ""
echo "==> Prometheus scrape targets"
if docker exec reportagent_prometheus wget -qO- http://localhost:9090/api/v1/targets 2>/dev/null | grep -q reportagent_fastapi; then
  echo "  OK   target reportagent_fastapi configured"
elif docker exec reportagent_prometheus curl -sf http://localhost:9090/api/v1/targets 2>/dev/null | grep -q reportagent_fastapi; then
  echo "  OK   target reportagent_fastapi configured"
else
  echo "  INFO check targets: docker exec reportagent_prometheus curl -s http://localhost:9090/api/v1/targets | head -c 500"
fi
