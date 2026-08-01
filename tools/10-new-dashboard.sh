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

[[ $# -gt 0 ]] || die "Usage: $0 DASHBOARD_NAME API_ENDPOINT [--repo PATH]"
[[ $# -ge 2 ]] || die "API endpoint required"

NAME="$1"
ENDPOINT="$2"
shift 2

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo) REPO="$2"; PORTAL="$REPO/platform-portal"; shift 2 ;;
    --help|-h) echo "Usage: $0 DASHBOARD_NAME API_ENDPOINT [--repo PATH]"; exit 0 ;;
    *) die "Unknown option: $1" ;;
  esac
done

SNAKE="$(snake "$NAME")"
KEBAB="$(kebab "$NAME")"
CLASS="$(pascal "$NAME")"
TEMPLATE="$PORTAL/templates/${SNAKE}_dashboard.html"
JS_DIR="$PORTAL/static/js"
JS="$JS_DIR/${SNAKE}_dashboard.js"

mkdir -p "$JS_DIR"
[[ ! -e "$TEMPLATE" && ! -e "$JS" ]] || die "Dashboard already exists"

cat > "$TEMPLATE" <<HTML
{% extends "base.html" %}
{% block title %}${CLASS} Dashboard{% endblock %}
{% block heading %}${CLASS} Dashboard{% endblock %}
{% block subtitle %}Operational ${KEBAB} summary{% endblock %}
{% block content %}
<section class="grid metrics">
  <article class="card"><div class="label">Current value</div><div class="value" id="${SNAKE}-value">—</div></article>
  <article class="card"><div class="label">Status</div><div class="value small" id="${SNAKE}-status">Loading</div></article>
</section>
<section class="section">
  <div class="card" style="height:320px">
    <canvas id="${SNAKE}-chart"></canvas>
  </div>
</section>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<script src="{{ url_for('static', filename='js/${SNAKE}_dashboard.js') }}"></script>
{% endblock %}
HTML

cat > "$JS" <<JS
async function loadDashboard() {
  const response = await fetch("${ENDPOINT}", { cache: "no-store" });
  if (!response.ok) throw new Error("Dashboard API failed");
  return response.json();
}

loadDashboard().then(data => {
  document.getElementById("${SNAKE}-status").textContent = "Ready";
  document.getElementById("${SNAKE}-value").textContent =
    data.current ?? data.score ?? data.value ?? "—";

  const labels = data.labels || [];
  const values = data.values || [];

  new Chart(document.getElementById("${SNAKE}-chart"), {
    type: "line",
    data: {
      labels,
      datasets: [{ label: "${CLASS}", data: values, tension: 0.25 }]
    },
    options: { responsive: true, maintainAspectRatio: false }
  });
}).catch(error => {
  document.getElementById("${SNAKE}-status").textContent = error.message;
});
JS

ok "Dashboard scaffold created"
echo "Add a page route and navigation entry manually."
