#!/usr/bin/env bash
# Backup ReportAgent data (users.db, storage, chroma, secrets, .env).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKUP_ROOT="${BACKUP_ROOT:-$HOME/backups/reportagent}"
STAMP="$(date +%Y%m%d-%H%M%S)"
DEST="$BACKUP_ROOT/$STAMP"

mkdir -p "$DEST"

if [[ -f "$ROOT/app/data/users.db" ]]; then
  cp "$ROOT/app/data/users.db" "$DEST/"
fi
if [[ -f "$ROOT/.env" ]]; then
  cp "$ROOT/.env" "$DEST/"
fi
if [[ -d "$ROOT/storage" ]]; then
  tar czf "$DEST/storage.tar.gz" -C "$ROOT" storage
fi
if [[ -d "$ROOT/chroma_data" ]]; then
  tar czf "$DEST/chroma_data.tar.gz" -C "$ROOT" chroma_data
fi
if [[ -d "$ROOT/secrets" ]]; then
  tar czf "$DEST/secrets.tar.gz" -C "$ROOT" secrets
fi

echo "Backup saved to $DEST"
ls -la "$DEST"
