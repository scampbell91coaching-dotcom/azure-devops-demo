#!/usr/bin/env bash
set -euo pipefail
REPO="${1:-$HOME/azure-devops-demo}"
cd "$REPO"
rm -rf .core-task-backups
find . -type f \( -name '*.tfplan' -o -name 'deployment.yaml' \) -not -path './.git/*' -print -delete || true
find evidence -type d -empty -print -delete 2>/dev/null || true
git status --short
