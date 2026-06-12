#!/usr/bin/env bash
# Run on VPS: checks why grafana subdomain may show SMDG instead of Grafana.
set -euo pipefail

GRAFANA_DOMAIN="${GRAFANA_DOMAIN:-grafana.reportagent.fileguardian.info}"

NGINX="$(docker ps --format '{{.Names}}' | grep -i nginx | head -1 || true)"
if [[ -z "$NGINX" ]]; then
  echo "ERROR: no nginx container found"
  exit 1
fi

echo "==> nginx container: $NGINX"
echo "==> grafana domain:  $GRAFANA_DOMAIN"
echo ""

echo "==> 1. DNS"
dig +short "$GRAFANA_DOMAIN" A || true
echo ""

echo "==> 2. Grafana container networks"
docker inspect reportagent_grafana --format 'networks: {{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}' 2>/dev/null || echo "reportagent_grafana not running"
echo ""

echo "==> 3. nginx → reportagent_grafana (must return JSON with database=ok)"
if docker exec "$NGINX" curl -sf --max-time 10 "http://reportagent_grafana:3000/api/health" 2>/dev/null; then
  echo ""
  echo "  OK   nginx can reach Grafana container"
else
  echo "  FAIL nginx cannot reach reportagent_grafana:3000"
  echo "       Fix: EXTERNAL_NGINX_NETWORK in .env + ./deploy.sh"
fi
echo ""

echo "==> 4. Public HTTP Host header"
BODY="$(curl -sf --max-time 10 -H "Host: $GRAFANA_DOMAIN" "http://127.0.0.1/api/health" 2>/dev/null || true)"
if echo "$BODY" | grep -q '"database":"ok"'; then
  echo "  OK   HTTP returns Grafana JSON"
elif echo "$BODY" | grep -qi smdg; then
  echo "  FAIL HTTP returns SMDG — add nginx server_name $GRAFANA_DOMAIN"
else
  echo "  WARN unexpected response (add nginx server block — docs/nginx-grafana-smdg-setup.md)"
  echo "$BODY" | head -c 200
  echo ""
fi
echo ""

echo "==> 5. Public HTTPS"
if curl -sf --max-time 10 "https://${GRAFANA_DOMAIN}/api/health" 2>/dev/null | grep -q '"database":"ok"'; then
  echo "  OK   HTTPS Grafana"
else
  CODE="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "https://${GRAFANA_DOMAIN}/" 2>/dev/null || echo 000)"
  echo "  FAIL HTTPS (http_code=$CODE) — likely default server SMDG or cert mismatch"
  echo "       See docs/nginx-grafana-smdg-setup.md"
fi
