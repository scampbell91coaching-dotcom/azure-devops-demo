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
Usage: $0 [--repo PATH]

Checks the local development environment, Azure login, AKS access,
portal service, Git state and required CLIs.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo) REPO="$2"; PORTAL="$REPO/platform-portal"; shift 2 ;;
    --help|-h) usage; exit 0 ;;
    *) die "Unknown option: $1" ;;
  esac
done

require_repo

PASS=0
WARN=0
FAIL=0

check_cmd(){
  local tool="$1"
  if have "$tool"; then
    ok "$tool -> $(command -v "$tool")"; PASS=$((PASS+1))
  else
    warn "$tool missing"; WARN=$((WARN+1))
  fi
}

say "Core tools"
for tool in git python3 sqlite3 jq curl docker az terraform kubectl helm gh argocd; do
  check_cmd "$tool"
done

say "Quality and platform tools"
for tool in k9s stern kubectx kubens kubeconform actionlint shellcheck yamllint \
  checkov trivy cosign syft grype infracost istioctl node npm yarn mmdc; do
  check_cmd "$tool"
done

say "Repository"
if [[ -z "$(git -C "$REPO" status --porcelain)" ]]; then
  ok "Working tree clean"; PASS=$((PASS+1))
else
  warn "Working tree has local changes"; WARN=$((WARN+1))
  git -C "$REPO" status --short
fi

say "Portal"
if [[ -x "$PORTAL/.venv/bin/python" ]]; then
  ok "Portal virtualenv exists"; PASS=$((PASS+1))
else
  warn "Portal virtualenv missing"; WARN=$((WARN+1))
fi

if systemctl --user is-active --quiet platform-portal-flask.service 2>/dev/null; then
  ok "Portal service active"; PASS=$((PASS+1))
else
  warn "Portal service inactive"; WARN=$((WARN+1))
fi

if curl -fsS http://localhost:8090/health >/dev/null 2>&1; then
  ok "Portal health endpoint available"; PASS=$((PASS+1))
else
  warn "Portal health endpoint unavailable"; WARN=$((WARN+1))
fi

say "Azure and Kubernetes"
if az account show >/dev/null 2>&1; then
  ok "Azure CLI authenticated"; PASS=$((PASS+1))
else
  warn "Azure CLI not authenticated"; WARN=$((WARN+1))
fi

if kubectl cluster-info >/dev/null 2>&1; then
  ok "Kubernetes API reachable"; PASS=$((PASS+1))
else
  warn "Kubernetes API unreachable"; WARN=$((WARN+1))
fi

say "Summary"
echo "PASS=$PASS WARN=$WARN FAIL=$FAIL"
