#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT"

echo "==> Building ReportAgent documentation (MkDocs)"

if ! command -v mkdocs >/dev/null 2>&1; then
  VENV_DIR="${ROOT}/.venv-docs"
  if [[ ! -x "${VENV_DIR}/bin/mkdocs" ]]; then
    echo "==> Creating doc venv and installing dependencies"
    python3 -m venv "$VENV_DIR"
    "${VENV_DIR}/bin/pip" install -q -r docs/requirements-docs.txt
  fi
  export PATH="${VENV_DIR}/bin:${PATH}"
fi

mkdocs build

if [[ -f site/index.html ]]; then
  echo "==> Documentation built: site/ ($(du -sh site | cut -f1))"
else
  echo "ERROR: site/index.html not found after mkdocs build" >&2
  exit 1
fi
