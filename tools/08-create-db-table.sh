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
Usage: $0 TABLE_NAME [--repo PATH]

Creates a SQLAlchemy model, repository and test scaffold.
It does not generate an Alembic migration automatically.
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

SNAKE="$(snake "$NAME")"
CLASS="$(pascal "$NAME")"
MODEL_DIR="$PORTAL/portal/models"
MODEL="$MODEL_DIR/${SNAKE}.py"
REPO_FILE="$PORTAL/portal/repositories/${SNAKE}_repository.py"
TEST="$PORTAL/tests/test_${SNAKE}_model.py"

mkdir -p "$MODEL_DIR"
[[ -f "$MODEL_DIR/__init__.py" ]] || echo '"""Database models."""' > "$MODEL_DIR/__init__.py"

for path in "$MODEL" "$REPO_FILE" "$TEST"; do
  [[ ! -e "$path" ]] || die "Refusing to overwrite: $path"
done

cat > "$MODEL" <<PY
from __future__ import annotations

from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class ${CLASS}(db.Model):
    __tablename__ = "${SNAKE}"

    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
PY

cat > "$REPO_FILE" <<PY
from __future__ import annotations

from ..models.${SNAKE} import ${CLASS}, db


class ${CLASS}Repository:
    def list(self) -> list[${CLASS}]:
        return list(${CLASS}.query.order_by(${CLASS}.created_at.desc()).all())

    def add(self, item: ${CLASS}) -> ${CLASS}:
        db.session.add(item)
        db.session.commit()
        return item
PY

cat > "$TEST" <<PY
def test_${SNAKE}_model_scaffold_exists():
    from portal.models.${SNAKE} import ${CLASS}

    assert ${CLASS}.__tablename__ == "${SNAKE}"
PY

ok "Database scaffold created"
echo "Next:"
echo "1. Move db = SQLAlchemy() into a shared extension module"
echo "2. Register it in create_app()"
echo "3. Configure SQLALCHEMY_DATABASE_URI"
echo "4. Run: flask db migrate -m 'add ${SNAKE}'"
