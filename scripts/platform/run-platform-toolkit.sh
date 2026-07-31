#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="${1:-$HOME/azure-devops-demo}"
printf "1 Health\n2 Validate\n3 Drift\n4 Cleanup\n"
read -r -p "Task: " T
case "$T" in
1) exec "$HERE/platform-health.sh" ;;
2) exec "$HERE/validate-platform.sh" "$REPO" ;;
3) exec "$HERE/check-drift.sh" "$REPO" ;;
4) exec "$HERE/cleanup-repo.sh" "$REPO" ;;
*) exit 2 ;;
esac
