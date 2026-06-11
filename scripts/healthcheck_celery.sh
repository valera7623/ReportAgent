#!/usr/bin/env bash
set -euo pipefail

# Prefer Celery inspect ping; fall back to process check.
if celery -A app.celery_app inspect ping --timeout=5 2>/dev/null | grep -q "pong"; then
  exit 0
fi

if pgrep -f "celery.*worker" >/dev/null 2>&1; then
  exit 0
fi

exit 1
