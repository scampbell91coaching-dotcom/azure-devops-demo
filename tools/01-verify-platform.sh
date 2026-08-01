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
Usage: $0 [--repo PATH] [--fast]

Runs repository quality gates. --fast skips slower security scans.
EOF
}

FAST=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo) REPO="$2"; PORTAL="$REPO/platform-portal"; shift 2 ;;
    --fast) FAST=1; shift ;;
    --help|-h) usage; exit 0 ;;
    *) die "Unknown option: $1" ;;
  esac
done

require_repo
cd "$REPO"

PASS=0
FAIL=0

run_check(){
  local name="$1"; shift
  say "$name"
  if "$@"; then ok "$name"; PASS=$((PASS+1))
  else warn "$name"; FAIL=$((FAIL+1)); fi
}

run_check "Git diff check" git diff --check
run_check "ShellCheck" bash -c 'find tools scripts -type f -name "*.sh" -print0 2>/dev/null | xargs -0 -r shellcheck'
run_check "YAML lint" yamllint .github flask-app 2>/dev/null
run_check "GitHub Actions lint" actionlint
run_check "Terraform formatting" terraform -chdir=infra fmt -check -recursive
run_check "Terraform validation" terraform -chdir=infra validate
run_check "AKS Terraform validation" terraform -chdir=infra/aks validate
run_check "Helm lint" helm lint flask-app -f flask-app/values-production.yaml
run_check "Helm render" bash -c 'helm template flask-web-prod flask-app -f flask-app/values-production.yaml > /tmp/platform-rendered.yaml'
run_check "Kubernetes schema validation" kubeconform -strict -ignore-missing-schemas /tmp/platform-rendered.yaml

if [[ -x "$PORTAL/.venv/bin/python" ]]; then
  run_check "Portal tests" bash -c "cd '$PORTAL' && .venv/bin/pytest -q"
  run_check "Ruff" bash -c "cd '$PORTAL' && .venv/bin/ruff check ."
  run_check "Mypy" bash -c "cd '$PORTAL' && .venv/bin/mypy portal app.py --ignore-missing-imports"
else
  warn "Portal venv missing; Python checks skipped"
  FAIL=$((FAIL+1))
fi

if [[ "$FAST" != "1" ]]; then
  run_check "Checkov" checkov -d infra --quiet
  run_check "Trivy filesystem scan" trivy fs --severity HIGH,CRITICAL --ignore-unfixed .
fi

say "Summary"
echo "PASS=$PASS FAIL=$FAIL"
(( FAIL == 0 ))
