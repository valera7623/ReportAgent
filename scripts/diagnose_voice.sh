#!/usr/bin/env bash
# Diagnose voice/Whisper on VPS — run from ~/ReportAgent
set -euo pipefail

cd "$(dirname "$0")/.."

AUDIO="${1:-recording.wav}"
CONTAINER="${CONTAINER:-reportagent_fastapi}"

echo "=== Voice diagnostics ==="
echo

if [[ ! -f "$AUDIO" ]]; then
  echo "ERROR: audio file not found: $AUDIO"
  exit 1
fi

echo "1. Host file:"
ls -la "$AUDIO"
file "$AUDIO" || true
echo

echo "2. OpenAI / ProxyAPI config in container:"
docker exec "$CONTAINER" python3 -c "
import os
k = os.getenv('OPENAI_API_KEY', '')
base = os.getenv('OPENAI_BASE_URL', '') or '(default api.openai.com)'
print('  OPENAI_API_KEY set:', bool(k), '| length:', len(k))
print('  OPENAI_BASE_URL:', base)
if k and not k.startswith('sk-'):
    print('  WARNING: key does not start with sk-')
if not os.getenv('OPENAI_BASE_URL') and len(k) < 50:
    print('  HINT: short key without OPENAI_BASE_URL? Use ProxyAPI:')
    print('        OPENAI_BASE_URL=https://api.proxyapi.ru/openai/v1')
"
echo

echo "3. ffmpeg in container:"
docker exec "$CONTAINER" ffmpeg -version 2>/dev/null | head -1 || echo "  ffmpeg NOT FOUND"
echo

echo "4. Copy audio into container and test Whisper:"
BASENAME="$(basename "$AUDIO")"
docker cp "$AUDIO" "${CONTAINER}:/tmp/${BASENAME}"

docker exec "$CONTAINER" python3 -c "
import json
from app.voice.transcriber import transcribe_audio
r = transcribe_audio('/tmp/${BASENAME}')
print(json.dumps(r, ensure_ascii=False, indent=2))
"
echo

echo "5. Last voice log lines:"
docker exec "$CONTAINER" tail -15 /app/logs/log_voice.log 2>/dev/null || \
  tail -15 logs/log_voice.log 2>/dev/null || echo "  (no log_voice.log yet)"
echo

echo "=== Done ==="
