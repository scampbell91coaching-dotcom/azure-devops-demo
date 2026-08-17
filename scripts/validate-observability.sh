#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
default_rendered="$(mktemp)"
production_rendered="$(mktemp)"
monitoring_rendered="$(mktemp)"
service_monitor_only_rendered="$(mktemp)"
service_monitor_rendered="$(mktemp)"
rules_dir="$(mktemp -d)"
trap 'rm -f "$default_rendered" "$production_rendered" "$monitoring_rendered" "$service_monitor_only_rendered" "$service_monitor_rendered"; rm -rf "$rules_dir"' EXIT

helm lint "$repo_root/flask-app"
helm lint "$repo_root/flask-app" -f "$repo_root/flask-app/values-production.yaml"

helm template flask-web-default "$repo_root/flask-app" \
  --namespace default > "$default_rendered"
helm template flask-web-prod "$repo_root/flask-app" \
  --namespace production \
  -f "$repo_root/flask-app/values-production.yaml" > "$production_rendered"
helm template flask-web-monitoring "$repo_root/flask-app" \
  --namespace production \
  -f "$repo_root/flask-app/values-production.yaml" \
  --set monitoring.enabled=true \
  --set networkPolicy.allowMonitoring=true > "$monitoring_rendered"
helm template flask-web-service-monitor-only "$repo_root/flask-app" \
  --namespace production \
  -f "$repo_root/flask-app/values-production.yaml" \
  --set monitoring.serviceMonitor.enabled=true > "$service_monitor_only_rendered"
helm template flask-web-monitoring "$repo_root/flask-app" \
  --namespace production \
  -f "$repo_root/flask-app/values-production.yaml" \
  --set monitoring.enabled=true \
  --set monitoring.serviceMonitor.enabled=true \
  --set networkPolicy.allowMonitoring=true > "$service_monitor_rendered"

! grep -q '^kind: ServiceMonitor$' "$default_rendered"
! grep -q '^kind: ServiceMonitor$' "$production_rendered"
! grep -q '^kind: ServiceMonitor$' "$monitoring_rendered"
! grep -q '^kind: ServiceMonitor$' "$service_monitor_only_rendered"
grep -q '^kind: ServiceMonitor$' "$service_monitor_rendered"
grep -q '^kind: PrometheusRule$' "$monitoring_rendered"
grep -q '^  namespace: production$' "$monitoring_rendered"
grep -q '^kind: ConfigMap$' "$monitoring_rendered"
grep -q '^[[:space:]]*path: /metrics$' "$service_monitor_rendered"
grep -q '^[[:space:]]*interval: 30s$' "$service_monitor_rendered"
grep -q '^[[:space:]]*scrapeTimeout: 10s$' "$service_monitor_rendered"

probe_paths="$(awk '
  /^[[:space:]]+(startupProbe|readinessProbe|livenessProbe):$/ { probe=$1; next }
  probe != "" && /^[[:space:]]+path:/ { print probe, $2; probe="" }
' "$production_rendered")"
printf '%s\n' "$probe_paths" | grep -q '^startupProbe: /health$'
printf '%s\n' "$probe_paths" | grep -q '^readinessProbe: /health$'
printf '%s\n' "$probe_paths" | grep -q '^livenessProbe: /health$'
! grep -q 'name: METRICS_BEARER_TOKEN' "$production_rendered"
grep -q 'name: METRICS_BEARER_TOKEN' "$service_monitor_rendered"
grep -q '^[[:space:]]*authorization:$' "$service_monitor_rendered"
grep -q 'key: METRICS_BEARER_TOKEN' "$service_monitor_rendered"
grep -q 'alert: TraditionalStrengthDatabaseUnavailable' "$monitoring_rendered"
grep -q 'traditional_strength_dependency_available{namespace="production",dependency="database"}' "$monitoring_rendered"
grep -q 'alert: TraditionalStrengthLoginFailureBurst' "$monitoring_rendered"
grep -q 'alert: TraditionalStrengthTenantDenialAnomaly' "$monitoring_rendered"
grep -q 'alert: TraditionalStrengthStatusCollectorStale' "$monitoring_rendered"
grep -q 'page: "true"' "$monitoring_rendered"
grep -q 'page: "false"' "$monitoring_rendered"
grep -q 'absent(traditional_strength_dependency_available' "$monitoring_rendered"
grep -q 'absent(traditional_strength_dependency_last_check_timestamp_seconds' "$monitoring_rendered"
grep -q 'time() - min(traditional_strength_dependency_last_check_timestamp_seconds' "$monitoring_rendered"
grep -q 'absent(kube_cronjob_status_last_successful_time' "$monitoring_rendered"
grep -q 'health_status=~"Degraded|Missing"' "$monitoring_rendered"
! grep -q 'health_status=~"Degraded|Missing",sync_status!=' "$monitoring_rendered"
grep -q 'job_name="flask-web-monitoring-flask-app-migration"' "$monitoring_rendered"
! grep -q 'job_name=~".*migrat.*"' "$monitoring_rendered"
rules_file="$rules_dir/traditional-strength-rules.yaml"
python3 - "$monitoring_rendered" "$rules_file" <<'PY'
import sys, yaml
documents = yaml.safe_load_all(open(sys.argv[1], encoding="utf-8"))
rule = next(item for item in documents if item and item.get("kind") == "PrometheusRule")
with open(sys.argv[2], "w", encoding="utf-8") as destination:
    yaml.safe_dump({"groups": rule["spec"]["groups"]}, destination)
PY
if command -v promtool >/dev/null 2>&1; then
  promtool check rules "$rules_file"
  cp "$repo_root/tests/prometheus/traditional-strength.test.yml" "$rules_dir/rules.test.yml"
  promtool test rules "$rules_dir/rules.test.yml"
elif [[ "${REQUIRE_PROMTOOL:-false}" == "true" ]]; then
  echo "ERROR: promtool is required for authoritative PromQL validation." >&2
  exit 1
else
  echo "WARNING: promtool unavailable; local Helm/YAML and contract assertions ran, but authoritative PromQL checks did not. CI sets REQUIRE_PROMTOOL=true." >&2
fi
python3 -m json.tool \
  "$repo_root/flask-app/dashboards/traditional-strength-production.json" >/dev/null
echo "Observability compatibility probes, private scrape authentication, scoped paging, alert coverage, and dashboard JSON are valid."
