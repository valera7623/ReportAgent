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

echo "2. OPENAI_API_KEY in container (length only):"
docker exec "$CONTAINER" python3 -c "
import os
k = os.getenv('OPENAI_API_KEY', '')
print('  set:', bool(k), '| length:', len(k))
if k and not k.startswith('sk-'):
    print('  WARNING: key does not start with sk-')
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
