#!/usr/bin/env bash
set -Eeuo pipefail

REPO="${REPO:-$HOME/azure-devops-demo}"
PORTAL="$REPO/platform-portal"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

say(){ printf "\n${CYAN}==> %s${NC}\n" "$*"; }
ok(){ printf "${GREEN}PASS${NC} %s\n" "$*"; }
warn(){ printf "${YELLOW}WARN${NC} %s\n" "$*"; }
die(){ printf "${RED}ERROR${NC} %s\n" "$*" >&2; exit 1; }
have(){ command -v "$1" >/dev/null 2>&1; }

require_repo(){
  [[ -d "$REPO/.git" ]] || die "Git repository not found at $REPO"
}

require_clean(){
  require_repo
  [[ -z "$(git -C "$REPO" status --porcelain)" ]] || {
    git -C "$REPO" status --short
    die "Git working tree must be clean"
  }
}

snake(){
  printf '%s' "$1" \
    | tr '[:upper:]' '[:lower:]' \
    | sed -E 's/[^a-z0-9]+/_/g; s/^_+//; s/_+$//'
}

kebab(){
  printf '%s' "$1" \
    | tr '[:upper:]' '[:lower:]' \
    | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//'
}

pascal(){
  python3 - "$1" <<'PY'
import re, sys
parts = re.split(r'[^A-Za-z0-9]+', sys.argv[1])
print("".join(p[:1].upper() + p[1:] for p in parts if p))
PY
}

usage(){
  cat <<EOF
Usage: $0 API_NAME [--repo PATH]

Creates a versioned Flask API blueprint and test scaffold.
EOF
}

[[ $# -gt 0 ]] || { usage; exit 1; }
NAME="$1"; shift
while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo) REPO="$2"; PORTAL="$REPO/platform-portal"; shift 2 ;;
    --help|-h) usage; exit 0 ;;
    *) die "Unknown option: $1" ;;
  esac
done

require_repo
SNAKE="$(snake "$NAME")"
KEBAB="$(kebab "$NAME")"
API="$PORTAL/portal/api/${SNAKE}.py"
TEST="$PORTAL/tests/test_${SNAKE}_api.py"

[[ ! -e "$API" && ! -e "$TEST" ]] || die "API or test already exists"

cat > "$API" <<PY
from flask import Blueprint, jsonify

${SNAKE}_bp = Blueprint("${SNAKE}_api", __name__)


@${SNAKE}_bp.get("/${KEBAB}")
def get_${SNAKE}():
    return jsonify({"name": "${KEBAB}", "status": "ready"})
PY

cat > "$TEST" <<PY
from portal import create_app


def test_${SNAKE}_api_contract():
    app = create_app()
    client = app.test_client()
    assert client is not None
PY

ok "API scaffold created"
echo "Register ${SNAKE}_bp in portal/__init__.py with url_prefix='/api/v1'."
