#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT"

site_ready() {
  [[ -f site/index.html ]]
}

echo "==> Building ReportAgent documentation (MkDocs)"

if site_ready && [[ "${FORCE_DOCS_BUILD:-0}" != "1" ]]; then
  echo "==> site/index.html already present — skipping rebuild (set FORCE_DOCS_BUILD=1 to rebuild)"
  echo "==> Documentation ready: site/ ($(du -sh site | cut -f1))"
  exit 0
fi

build_with_mkdocs() {
  mkdocs build
}

build_with_venv() {
  local venv_dir="${ROOT}/.venv-docs"
  if [[ ! -x "${venv_dir}/bin/mkdocs" ]]; then
    echo "==> Creating doc venv"
    if ! python3 -m venv "$venv_dir" 2>/dev/null; then
      return 1
    fi
    "${venv_dir}/bin/pip" install -q -r docs/requirements-docs.txt
  fi
  "${venv_dir}/bin/mkdocs" build
}

build_with_pip_user() {
  echo "==> Installing MkDocs via pip --user"
  python3 -m pip install --user -q -r docs/requirements-docs.txt
  local user_bin
  user_bin="$(python3 -m site --user-base 2>/dev/null)/bin"
  if [[ -x "${user_bin}/mkdocs" ]]; then
    "${user_bin}/mkdocs" build
  elif command -v mkdocs >/dev/null 2>&1; then
    mkdocs build
  else
    return 1
  fi
}

build_with_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    return 1
  fi
  echo "==> Building docs inside Docker (python:3.12-slim)"
  docker run --rm \
    -v "${ROOT}:/work" \
    -w /work \
    python:3.12-slim \
    bash -lc "pip install -q -r docs/requirements-docs.txt && mkdocs build"
}

build_failed=1

if command -v mkdocs >/dev/null 2>&1 && build_with_mkdocs; then
  build_failed=0
elif build_with_venv; then
  build_failed=0
elif build_with_pip_user; then
  build_failed=0
elif build_with_docker; then
  build_failed=0
fi

if site_ready; then
  echo "==> Documentation ready: site/ ($(du -sh site | cut -f1))"
  exit 0
fi

if [[ "$build_failed" -eq 1 ]]; then
  echo "ERROR: Could not build documentation and site/index.html is missing." >&2
  echo "       Options:" >&2
  echo "         1. Commit site/ from CI or local: ./scripts/build-docs.sh && git add site/" >&2
  echo "         2. On VPS: apt install python3-venv python3-pip && FORCE_DOCS_BUILD=1 ./scripts/build-docs.sh" >&2
  echo "         3. Ensure Docker is available (used as fallback builder)" >&2
  exit 1
fi

echo "ERROR: site/index.html not found after mkdocs build" >&2
exit 1
