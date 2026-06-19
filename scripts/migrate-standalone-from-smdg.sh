#!/usr/bin/env bash
# Disconnect ReportAgent from SMDG Docker network and redeploy standalone.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> Disconnecting ReportAgent containers from SMDG networks"
for c in reportagent_fastapi reportagent_grafana reportagent_celery_worker reportagent_celery_beat; do
  for net in smdg_frontend smdg_backend smdg_default; do
    docker network disconnect "$net" "$c" 2>/dev/null || true
  done
done

if [[ -f .env ]]; then
  sed -i '/^EXTERNAL_NGINX_NETWORK=/d' .env
  grep -q '^TRAEFIK_ENABLED=' .env && sed -i 's/^TRAEFIK_ENABLED=.*/TRAEFIK_ENABLED=false/' .env || echo 'TRAEFIK_ENABLED=false' >> .env
fi

echo "==> Redeploying standalone stack"
./deploy.sh

echo ""
echo "==> Networks (should NOT include smdg_*):"
docker inspect reportagent_fastapi --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}'

echo ""
echo "==> Host ports"
docker port reportagent_fastapi 2>/dev/null || true
docker port reportagent_grafana 2>/dev/null || true

echo ""
echo "Next: add docs/smdg-edge-proxy.example.conf to ~/SMDG/nginx-https.conf and reload smdg-nginx-1"
