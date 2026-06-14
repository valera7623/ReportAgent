#!/usr/bin/env bash
set -euo pipefail

# Celery beat has no HTTP server — check the beat process is running.
if pgrep -f "celery.*beat" >/dev/null 2>&1; then
  exit 0
fi

exit 1
