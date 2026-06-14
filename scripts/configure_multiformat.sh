#!/usr/bin/env bash
# Configure Notion + Google Slides credentials on VPS.
# Run on VPS: cd ~/ReportAgent && ./scripts/configure_multiformat.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT"

ENV_FILE="${ROOT}/.env"
SECRETS_DIR="${ROOT}/secrets"
SA_FILE="${SECRETS_DIR}/google-sa.json"

echo "==> ReportAgent multi-format credentials setup"
echo "    Project: $ROOT"
echo ""

mkdir -p "$SECRETS_DIR" storage/formatted
chmod 700 "$SECRETS_DIR"

set_env() {
  local key="$1"
  local val="$2"
  if grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
    sed -i "s|^${key}=.*|${key}=${val}|" "$ENV_FILE"
  else
    echo "${key}=${val}" >> "$ENV_FILE"
  fi
}

run_in_worker() {
  local script="$1"
  docker cp "$script" reportagent_celery_worker:/tmp/setup_script.py
  docker exec reportagent_celery_worker python3 /tmp/setup_script.py
}

# --- Notion ---
echo "--- Notion ---"
echo "1. Create integration: https://www.notion.so/my-integrations"
echo "2. Create a database with title property 'Name'"
echo "3. Share database with your integration (Invite)"
echo ""
read -r -p "NOTION_INTEGRATION_TOKEN (secret_... or Enter to skip): " NOTION_TOKEN
if [[ -n "$NOTION_TOKEN" ]]; then
  set_env NOTION_INTEGRATION_TOKEN "$NOTION_TOKEN"
  export NOTION_INTEGRATION_TOKEN="$NOTION_TOKEN"

  read -r -p "NOTION_DATABASE_ID (32-char hex or Enter to auto-discover): " NOTION_DB
  if [[ -z "$NOTION_DB" ]]; then
    echo "Discovering databases..."
    run_in_worker scripts/setup_notion.py || python3 scripts/setup_notion.py || true
    read -r -p "Paste NOTION_DATABASE_ID from output: " NOTION_DB
  fi
  if [[ -n "$NOTION_DB" ]]; then
    set_env NOTION_DATABASE_ID "$NOTION_DB"
    export NOTION_DATABASE_ID="$NOTION_DB"
    echo "Testing Notion connection..."
    NOTION_INTEGRATION_TOKEN="$NOTION_TOKEN" NOTION_DATABASE_ID="$NOTION_DB" \
      docker cp scripts/setup_notion.py reportagent_celery_worker:/tmp/setup_notion.py
    docker exec -e NOTION_INTEGRATION_TOKEN -e NOTION_DATABASE_ID \
      reportagent_celery_worker python3 /tmp/setup_notion.py || true
  fi
else
  echo "Skipped Notion."
fi

echo ""
echo "--- Google Slides ---"
echo "1. Google Cloud Console → enable Slides API + Drive API"
echo "2. Service account → Keys → JSON → save as secrets/google-sa.json"
echo "3. Create Slides template with placeholders: %DATE%, %METRICS%, %CHART_1%"
echo "4. Share template with service account email (Editor)"
echo ""

if [[ -f "$SA_FILE" ]]; then
  echo "Found $SA_FILE"
else
  echo "Upload JSON from your laptop:"
  echo "  scp -i ~/.ssh/reportagent_deploy ./google-sa.json smdg@74.208.252.225:~/ReportAgent/secrets/google-sa.json"
  read -r -p "Press Enter when google-sa.json is uploaded (or skip with Ctrl+C)..." _
fi

if [[ -f "$SA_FILE" ]]; then
  chmod 600 "$SA_FILE"
  set_env GOOGLE_SERVICE_ACCOUNT_JSON "/app/secrets/google-sa.json"
  export GOOGLE_SERVICE_ACCOUNT_JSON="/app/secrets/google-sa.json"

  read -r -p "GOOGLE_SLIDES_TEMPLATE_ID (from Slides URL or Enter to skip): " TEMPLATE_ID
  if [[ -n "$TEMPLATE_ID" ]]; then
    set_env GOOGLE_SLIDES_TEMPLATE_ID "$TEMPLATE_ID"
    export GOOGLE_SLIDES_TEMPLATE_ID="$TEMPLATE_ID"
    docker cp scripts/setup_google_slides.py reportagent_celery_worker:/tmp/setup_google_slides.py
    docker exec -e GOOGLE_SERVICE_ACCOUNT_JSON -e GOOGLE_SLIDES_TEMPLATE_ID \
      reportagent_celery_worker python3 /tmp/setup_google_slides.py || true
  fi
else
  echo "Skipped Google Slides (no SA file)."
fi

echo ""
echo "==> Restarting workers to pick up new env"
docker compose -f docker-compose.prod.yml -f docker-compose.prod.external-nginx.yml \
  --profile observability-host up -d fastapi celery_worker celery_beat 2>/dev/null || \
  docker compose -f docker-compose.prod.yml --profile observability-host up -d fastapi celery_worker celery_beat

echo ""
echo "==> Done. Test formats:"
echo "  docker cp scripts/test_formats.py reportagent_celery_worker:/tmp/test_formats.py"
echo "  docker exec reportagent_celery_worker python3 /tmp/test_formats.py"
echo ""
echo "API example (Excel):"
echo '  curl -X POST https://reportagent.fileguardian.info/generate_report \'
echo '    -H "X-API-Key: YOUR_KEY" -F "file=@sample.csv" -F "output_format=excel"'
