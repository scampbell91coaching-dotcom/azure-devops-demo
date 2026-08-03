#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
render_dir="$(mktemp -d)"
trap 'rm -rf "$render_dir"' EXIT

for command_name in helm kubeconform; do
  command -v "$command_name" >/dev/null || {
    echo "ERROR: $command_name is required" >&2
    exit 1
  }
done

helm lint "$repo_root/flask-app" --strict
helm lint "$repo_root/flask-app" --strict -f "$repo_root/flask-app/values-production.yaml"
helm lint "$repo_root/lead-magnets-chart" --strict

helm template flask-web "$repo_root/flask-app" --namespace demo >"$render_dir/flask.yaml"
helm template flask-web-prod "$repo_root/flask-app" --namespace production \
  -f "$repo_root/flask-app/values-production.yaml" >"$render_dir/flask-production.yaml"
helm template lead-magnets "$repo_root/lead-magnets-chart" --namespace production \
  >"$render_dir/lead-magnets.yaml"

if helm template mutable-image "$repo_root/flask-app" --set-string image.tag=latest \
  >"$render_dir/mutable.yaml" 2>/dev/null; then
  echo "ERROR: flask-app accepted the mutable latest image tag" >&2
  exit 1
fi

if helm template mutable-image "$repo_root/lead-magnets-chart" --set-string image.tag=latest \
  >"$render_dir/mutable.yaml" 2>/dev/null; then
  echo "ERROR: lead-magnets-chart accepted the mutable latest image tag" >&2
  exit 1
fi

schema_probe="https://raw.githubusercontent.com/yannh/kubernetes-json-schema/master/v1.31.0-standalone-strict/deployment-apps-v1.json"
if curl --fail --silent --show-error --max-time 5 --output /dev/null "$schema_probe"; then
  kubeconform -kubernetes-version 1.31.0 -strict -summary \
    "$render_dir/flask.yaml" "$render_dir/flask-production.yaml" "$render_dir/lead-magnets.yaml"
  kubeconform -kubernetes-version 1.31.0 -strict -summary -ignore-missing-schemas \
    "$repo_root/kubernetes" "$repo_root/private-platform-manifests"
else
  echo "WARNING: schema registry is unreachable; Helm YAML rendering and security assertions will still run" >&2
fi

rendered="$render_dir/all.yaml"
cat "$render_dir/flask.yaml" "$render_dir/flask-production.yaml" \
  "$render_dir/lead-magnets.yaml" >"$rendered"

awk 'BEGIN { RS="---" }
  /(^|\n)kind: (Deployment|Job)(\n|$)/ {
    required[1]="automountServiceAccountToken: false"
    required[2]="runAsNonRoot: true"
    required[3]="allowPrivilegeEscalation: false"
    required[4]="readOnlyRootFilesystem: true"
    required[5]="type: RuntimeDefault"
    required[6]="drop:"
    required[7]="resources:"
    for (i=1; i<=7; i++) if (index($0, required[i]) == 0) {
      print "ERROR: workload missing " required[i] > "/dev/stderr"; failed=1
    }
  }
  END { exit failed }' "$rendered"

awk 'BEGIN { RS="---" }
  /(^|\n)kind: Ingress(\n|$)/ {
    if (index($0, "tls:") == 0 || index($0, "force-ssl-redirect: \"true\"") == 0 ||
        index($0, "hsts: \"true\"") == 0 || index($0, "x-content-type-options: \"nosniff\"") == 0) {
      print "ERROR: ingress is not TLS-only with required security headers" > "/dev/stderr"; failed=1
    }
  }
  END { exit failed }' "$rendered"

if grep -REn 'image:[[:space:]]*[^[:space:]]+:(latest|main|master)([[:space:]]|$)' \
  "$repo_root" --include='*.yaml' --include='*.yml' --exclude-dir='.git'; then
  echo "ERROR: mutable workload image tag found" >&2
  exit 1
fi

echo "Security validation passed: Helm lint/render, workload controls, ingress TLS, and immutable images."
