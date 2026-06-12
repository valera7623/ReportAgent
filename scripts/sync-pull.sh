#!/usr/bin/env bash
# Pull latest code from GitHub and optionally redeploy.
# Usage:
#   ./scripts/sync-pull.sh          # localhost: pull only
#   ./scripts/sync-pull.sh --deploy # VPS/production: pull + ./deploy.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT"

DEPLOY=false
if [[ "${1:-}" == "--deploy" ]]; then
  DEPLOY=true
fi

echo "==> ReportAgent sync (pull from GitHub)"
echo "    path: $ROOT"
echo "    branch: $(git branch --show-current)"

if [[ -n "$(git status --porcelain)" ]]; then
  echo ""
  echo "WARNING: uncommitted local changes:"
  git status -s
  echo ""
  read -r -p "Continue pull? [y/N] " ans
  [[ "${ans,,}" == "y" ]] || exit 1
fi

git fetch origin
git pull --ff-only origin "$(git branch --show-current)"

echo ""
echo "==> Up to date: $(git log -1 --oneline)"

if [[ "$DEPLOY" == "true" ]]; then
  chmod +x deploy.sh deploy-dev.sh scripts/*.sh 2>/dev/null || true
  ./deploy.sh
fi
