#!/usr/bin/env bash
set -euo pipefail

REPO="${1:-$HOME/azure-devops-demo}"
PORT="${PORT:-8090}"

cd "$REPO/portal"
echo "Serving Platform Portal at http://localhost:$PORT"
python3 -m http.server "$PORT" --bind 0.0.0.0
