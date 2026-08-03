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

rendered_charts=(
  "$render_dir/flask.yaml"
  "$render_dir/flask-production.yaml"
  "$render_dir/lead-magnets.yaml"
)

# Validate built-in resources without relaxing missing-schema failures whenever
# the Kubernetes schema registry is reachable. Offline runs still pass every
# document through kubeconform's strict decoder, which rejects duplicate keys.
schema_probe="https://raw.githubusercontent.com/yannh/kubernetes-json-schema/master/v1.31.0-standalone-strict/deployment-apps-v1.json"
if command -v curl >/dev/null && \
  curl --fail --silent --show-error --max-time 5 --output /dev/null "$schema_probe"; then
  kubeconform -kubernetes-version 1.31.0 -strict -summary \
    -skip ServiceMonitor,PrometheusRule "${rendered_charts[@]}"
else
  echo "WARNING: Kubernetes schema registry is unreachable; running strict YAML decoding without built-in schema checks" >&2
  kubeconform -kubernetes-version 1.31.0 -strict -summary \
    -ignore-missing-schemas -schema-location 'file:///schema-registry-unavailable/{{.ResourceKind}}.json' \
    -skip ServiceMonitor,PrometheusRule "${rendered_charts[@]}"
fi

external_resources="$render_dir/external-resources.yaml"
awk 'BEGIN { RS="---" }
  /(^|\n)kind: (ServiceMonitor|PrometheusRule)(\n|$)/ {
    print "---" $0
  }' "${rendered_charts[@]}" >"$external_resources"

# Prometheus Operator schemas are external to Kubernetes' built-in schema set.
# Missing catalog entries are reported as skipped, while any schema that is
# available is still applied in strict mode and invalid resources still fail.
crd_catalog='https://raw.githubusercontent.com/datreeio/CRDs-catalog/main/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json'
validate_external_schemas() {
  local label="$1"
  shift
  local validation_output="$render_dir/${label}-schema-validation.txt"

  if kubeconform -kubernetes-version 1.31.0 -strict -summary -verbose \
    -ignore-filename-pattern '(^|/)values[^/]*\.ya?ml$' \
    -ignore-missing-schemas -schema-location default -schema-location "$crd_catalog" \
    "$@" >"$validation_output" 2>&1; then
    cat "$validation_output"
    return
  fi

  # A registry transport failure is not evidence that a resource is invalid.
  # Only downgrade failures when every reported validation failure is a schema
  # download error; malformed YAML and schema violations still fail the script.
  if grep -q 'failed validation: failed downloading schema' "$validation_output" && \
    ! grep 'failed validation:' "$validation_output" | \
      grep -qv 'failed validation: failed downloading schema'; then
    cat "$validation_output" >&2
    echo "WARNING: $label external CRD schemas are unavailable; strict YAML decoding still applies" >&2
    kubeconform -strict -summary -ignore-missing-schemas \
      -ignore-filename-pattern '(^|/)values[^/]*\.ya?ml$' \
      -schema-location 'file:///external-schema-unavailable/{{.ResourceKind}}.json' "$@"
    return
  fi

  cat "$validation_output" >&2
  return 1
}

validate_external_schemas rendered-crds "$external_resources"

# These directories contain several operator-owned resources whose schemas are
# not maintained by this repository. Built-in and available CRD schemas remain
# strict; only genuinely unavailable external schemas are skipped.
validate_external_schemas repository-manifests \
  "$repo_root/kubernetes" "$repo_root/private-platform-manifests"

rendered="$render_dir/all.yaml"
cat "${rendered_charts[@]}" >"$rendered"

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
