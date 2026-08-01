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
  echo "Usage: $0 CHART_NAME API_ENDPOINT [--repo PATH]"
}
[[ $# -ge 2 ]] || { usage; exit 1; }

NAME="$1"
ENDPOINT="$2"
shift 2

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo) REPO="$2"; PORTAL="$REPO/platform-portal"; shift 2 ;;
    --help|-h) usage; exit 0 ;;
    *) die "Unknown option: $1" ;;
  esac
done

SNAKE="$(snake "$NAME")"
CLASS="$(pascal "$NAME")"
JS_DIR="$PORTAL/static/js"
JS="$JS_DIR/${SNAKE}_chart.js"
[[ ! -e "$JS" ]] || die "Chart already exists: $JS"
mkdir -p "$JS_DIR"

cat > "$JS" <<JS
async function load${CLASS}Chart() {
  const response = await fetch("${ENDPOINT}", { cache: "no-store" });
  if (!response.ok) throw new Error("Unable to load ${CLASS} chart data");
  return response.json();
}

load${CLASS}Chart().then(data => {
  const canvas = document.getElementById("${SNAKE}-chart");
  if (!canvas || typeof Chart === "undefined") return;

  new Chart(canvas, {
    type: "line",
    data: {
      labels: data.labels || [],
      datasets: [{
        label: "${CLASS}",
        data: data.values || [],
        tension: 0.25
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false
    }
  });
});
JS

ok "Created $JS"
echo "Add <canvas id=\"${SNAKE}-chart\"></canvas> to a template."
echo "Ensure Chart.js is loaded by the page."
