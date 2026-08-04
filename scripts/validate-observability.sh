#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
default_rendered="$(mktemp)"
production_rendered="$(mktemp)"
monitoring_rendered="$(mktemp)"
service_monitor_only_rendered="$(mktemp)"
service_monitor_rendered="$(mktemp)"
trap 'rm -f "$default_rendered" "$production_rendered" "$monitoring_rendered" "$service_monitor_only_rendered" "$service_monitor_rendered"' EXIT

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
grep -q '^kind: ConfigMap$' "$monitoring_rendered"
grep -q '^[[:space:]]*path: /metrics$' "$service_monitor_rendered"
grep -q '^[[:space:]]*interval: 30s$' "$service_monitor_rendered"
grep -q '^[[:space:]]*scrapeTimeout: 10s$' "$service_monitor_rendered"

probe_paths="$(awk '
  /^[[:space:]]+(startupProbe|readinessProbe|livenessProbe):$/ { probe=$1; next }
  probe != "" && /^[[:space:]]+path:/ { print probe, $2; probe="" }
' "$production_rendered")"
test "$(printf '%s\n' "$probe_paths" | grep -c '/health')" -eq 3
printf '%s\n' "$probe_paths" | grep -q '^readinessProbe: /health$'
python3 -m json.tool \
  "$repo_root/flask-app/dashboards/traditional-strength-production.json" >/dev/null
echo "Observability Helm defaults, production probes, opt-in resources, and dashboard JSON are valid."
