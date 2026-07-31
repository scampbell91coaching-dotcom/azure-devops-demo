#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-evidence}"

find "$ROOT" -type f \
  \( -name "*.txt" -o -name "*.yaml" -o -name "*.yml" -o -name "*.json" -o -name "*.html" \) \
  -print0 |
while IFS= read -r -d '' file; do
  sed -E -i \
    -e 's/\b([0-9]{1,3}\.){3}[0-9]{1,3}\b/<REDACTED_IP>/g' \
    -e 's/aks-[A-Za-z0-9._-]+/<REDACTED_NODE>/g' \
    -e 's/[A-Za-z0-9._-]+\.azurecr\.io/<REDACTED_ACR>/g' \
    -e 's/[A-Za-z0-9._-]+\.vault\.azure\.net/<REDACTED_KEYVAULT>/g' \
    "$file"
done

echo "Evidence sanitised under: $ROOT"
