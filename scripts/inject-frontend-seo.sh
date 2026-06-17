#!/usr/bin/env bash
# Inject GA4, Yandex Metrika and SITE_URL into frontend/index.html from .env (run on VPS after deploy).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="${1:-$ROOT/.env}"
INDEX="$ROOT/frontend/index.html"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "No .env at $ENV_FILE — skip SEO inject"
  exit 0
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

DOMAIN="${DOMAIN:-}"
GA4="${GA4_MEASUREMENT_ID:-}"
YM="${YANDEX_METRIKA_ID:-}"
SITE="${SITE_URL:-}"
if [[ -z "$SITE" && -n "$DOMAIN" ]]; then
  SITE="https://${DOMAIN}"
fi

BLOCK="  <script>
    window.REPORTAGENT_SITE_URL = '${SITE}';
    window.REPORTAGENT_GA4_ID = '${GA4}';
    window.REPORTAGENT_YM_ID = '${YM}';
  </script>"

python3 - "$INDEX" "$BLOCK" <<'PY'
import re
import sys
from pathlib import Path

index = Path(sys.argv[1])
block = sys.argv[2]
text = index.read_text(encoding="utf-8")
pattern = (
    r"  <!-- Optional: analytics.*?  </script>\n"
    r"|  <script>\n    window\.REPORTAGENT_SITE_URL = .*?  </script>\n"
)
if not re.search(pattern, text, re.DOTALL):
    print("SEO inject block not found in index.html", file=sys.stderr)
    sys.exit(1)
text = re.sub(pattern, block + "\n", text, count=1, flags=re.DOTALL)
index.write_text(text, encoding="utf-8")
print(f"Updated {index}")
PY
