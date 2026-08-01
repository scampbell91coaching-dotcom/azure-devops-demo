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
Usage: $0 FEATURE_NAME [--repo PATH]

Creates a portal feature skeleton:
- service
- repository
- API blueprint
- template
- JavaScript module
- tests

It does not automatically register the blueprint or navigation.
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
[[ -d "$PORTAL/portal" ]] || die "Portal package missing at $PORTAL/portal"

SNAKE="$(snake "$NAME")"
KEBAB="$(kebab "$NAME")"
CLASS="$(pascal "$NAME")"

SERVICE="$PORTAL/portal/services/${SNAKE}.py"
REPOSITORY="$PORTAL/portal/repositories/${SNAKE}_repository.py"
API="$PORTAL/portal/api/${SNAKE}.py"
TEMPLATE="$PORTAL/templates/${SNAKE}.html"
JS_DIR="$PORTAL/static/js"
JS="$JS_DIR/${SNAKE}.js"
TEST="$PORTAL/tests/test_${SNAKE}.py"

for path in "$SERVICE" "$REPOSITORY" "$API" "$TEMPLATE" "$JS" "$TEST"; do
  [[ ! -e "$path" ]] || die "Refusing to overwrite: $path"
done

mkdir -p "$JS_DIR"

cat > "$REPOSITORY" <<PY
from __future__ import annotations

from typing import Any


class ${CLASS}Repository:
    def list(self) -> list[dict[str, Any]]:
        return []
PY

cat > "$SERVICE" <<PY
from __future__ import annotations

from typing import Any

from ..repositories.${SNAKE}_repository import ${CLASS}Repository


class ${CLASS}Service:
    def __init__(self, repository: ${CLASS}Repository | None = None) -> None:
        self.repository = repository or ${CLASS}Repository()

    def get_all(self) -> list[dict[str, Any]]:
        return self.repository.list()
PY

cat > "$API" <<PY
from flask import Blueprint, jsonify

from ..services.${SNAKE} import ${CLASS}Service

${SNAKE}_bp = Blueprint("${SNAKE}_api", __name__)
service = ${CLASS}Service()


@${SNAKE}_bp.get("/${KEBAB}")
def list_${SNAKE}():
    return jsonify({"items": service.get_all()})
PY

cat > "$TEMPLATE" <<HTML
{% extends "base.html" %}
{% block title %}${CLASS}{% endblock %}
{% block heading %}${CLASS}{% endblock %}
{% block subtitle %}Platform ${KEBAB} capability{% endblock %}
{% block content %}
<section class="section">
  <div class="card">
    <p id="${KEBAB}-status">Loading…</p>
  </div>
</section>
<script src="{{ url_for('static', filename='js/${SNAKE}.js') }}"></script>
{% endblock %}
HTML

cat > "$JS" <<JS
async function load${CLASS}() {
  const response = await fetch("/api/v1/${KEBAB}", { cache: "no-store" });
  if (!response.ok) throw new Error("Unable to load ${KEBAB}");
  return response.json();
}

load${CLASS}()
  .then(data => {
    document.getElementById("${KEBAB}-status").textContent =
      \`\${data.items.length} items loaded\`;
  })
  .catch(error => {
    document.getElementById("${KEBAB}-status").textContent = error.message;
  });
JS

cat > "$TEST" <<PY
from portal import create_app


def test_${SNAKE}_page_contract():
    app = create_app()
    client = app.test_client()

    # Register the generated blueprint before enabling this test.
    assert client is not None
PY

ok "Feature scaffold created for $NAME"
echo
echo "Next manual steps:"
echo "1. Register ${SNAKE}_bp in portal/__init__.py under /api/v1"
echo "2. Add a page route in portal/views.py"
echo "3. Add navigation to templates/base.html"
echo "4. Implement repository behaviour"
echo "5. Replace the placeholder test"
