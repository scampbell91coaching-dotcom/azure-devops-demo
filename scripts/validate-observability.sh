#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
rendered="$(mktemp)"
trap 'rm -f "$rendered"' EXIT

helm lint "$repo_root/flask-app" \
  -f "$repo_root/flask-app/values-production.yaml" \
  --set monitoring.enabled=true
helm template flask-web-prod "$repo_root/flask-app" \
  --namespace production \
  -f "$repo_root/flask-app/values-production.yaml" \
  --set monitoring.enabled=true > "$rendered"
grep -q '^kind: PrometheusRule$' "$rendered"
grep -q '^kind: ConfigMap$' "$rendered"
python3 -m json.tool \
  "$repo_root/flask-app/dashboards/traditional-strength-production.json" >/dev/null
echo "Observability Helm templates and dashboard JSON are valid."
