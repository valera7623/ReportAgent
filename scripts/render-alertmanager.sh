#!/usr/bin/env bash
# Render alertmanager.yml from template using .env variables.
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

TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
TELEGRAM_CHAT_ID="${TELEGRAM_CHAT_ID:-}"
ALERTS_ENABLED="${ALERTS_ENABLED:-true}"

TEMPLATE="alertmanager/alertmanager.yml.template"
OUTPUT="alertmanager/alertmanager.yml"

if [[ ! -f "$TEMPLATE" ]]; then
  echo "ERROR: $TEMPLATE not found" >&2
  exit 1
fi

mkdir -p alertmanager

if [[ "$ALERTS_ENABLED" != "true" ]] || [[ -z "$TELEGRAM_BOT_TOKEN" ]] || [[ -z "$TELEGRAM_CHAT_ID" ]]; then
  echo "==> Alerts disabled or Telegram not configured — writing noop alertmanager config"
  cat >"$OUTPUT" <<'EOF'
route:
  receiver: blackhole
receivers:
  - name: blackhole
EOF
  exit 0
fi

export TELEGRAM_BOT_TOKEN TELEGRAM_CHAT_ID
envsubst '${TELEGRAM_BOT_TOKEN} ${TELEGRAM_CHAT_ID}' <"$TEMPLATE" >"$OUTPUT"
echo "==> Rendered $OUTPUT"
