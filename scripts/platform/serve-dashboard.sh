#!/usr/bin/env bash
set -euo pipefail

REPO="${1:-$HOME/azure-devops-demo}"
PORT="${PORT:-8088}"
DASHBOARD_DIR="$REPO/dashboard"

[[ -f "$DASHBOARD_DIR/index.html" ]] || {
  echo "Dashboard missing. Generate it first:"
  echo "$REPO/scripts/platform/generate-dashboard.sh $REPO"
  exit 1
}

echo "Serving dashboard at:"
echo "  http://localhost:$PORT"
echo
echo "Press Ctrl+C to stop."

cd "$DASHBOARD_DIR"
python3 -m http.server "$PORT" --bind 127.0.0.1
