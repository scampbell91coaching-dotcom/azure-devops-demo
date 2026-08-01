#!/usr/bin/env bash
set -Eeuo pipefail

REPO="${REPO:-$HOME/azure-devops-demo}"

cd "$REPO"

checkov \
  --directory infra \
  --quiet
