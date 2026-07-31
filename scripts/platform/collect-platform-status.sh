#!/usr/bin/env bash
set -euo pipefail

REPO="${1:-$HOME/azure-devops-demo}"
NAMESPACE="${NAMESPACE:-production}"
DEPLOYMENT="${DEPLOYMENT:-flask-web}"
SERVICE="${SERVICE:-flask-web-prod-flask-app}"
INGRESS="${INGRESS:-flask-web-prod}"
ARGO_APP="${ARGO_APP:-flask-web-production}"
URL="${URL:-https://traditionalstrength.co.uk/health}"

OUT_DIR="$REPO/portal/data"
OUT_FILE="$OUT_DIR/platform-status.json"

cd "$REPO"
mkdir -p "$OUT_DIR"

json_bool() {
  [[ "$1" == "True" ]] && printf 'True' || printf 'False'
}

KUBE_API=False
kubectl cluster-info >/dev/null 2>&1 && KUBE_API=True

NODE_TOTAL=$(kubectl get nodes --no-headers 2>/dev/null | wc -l | tr -d ' ')
NODE_READY=$(kubectl get nodes --no-headers 2>/dev/null | awk '$2=="Ready"{c++} END{print c+0}')

READY=$(kubectl get deployment "$DEPLOYMENT" -n "$NAMESPACE" \
  -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo 0)
DESIRED=$(kubectl get deployment "$DEPLOYMENT" -n "$NAMESPACE" \
  -o jsonpath='{.spec.replicas}' 2>/dev/null || echo 0)

RESTARTS=$(kubectl get pods -n "$NAMESPACE" -l app=flask-web \
  -o jsonpath='{range .items[*]}{range .status.containerStatuses[*]}{.restartCount}{"\n"}{end}{end}' 2>/dev/null \
  | awk '{s+=$1} END{print s+0}')

SERVICE_TYPE=$(kubectl get svc "$SERVICE" -n "$NAMESPACE" \
  -o jsonpath='{.spec.type}' 2>/dev/null || echo unknown)

INGRESS_EXISTS=False
kubectl get ingress "$INGRESS" -n "$NAMESPACE" >/dev/null 2>&1 && INGRESS_EXISTS=True

NETWORK_POLICIES=$(kubectl get networkpolicy -n "$NAMESPACE" --no-headers 2>/dev/null | wc -l | tr -d ' ')

HTTP_CODE=$(curl -o /dev/null -sS -w '%{http_code}' --max-time 10 "$URL" 2>/dev/null || echo 000)
LATENCY=$(curl -o /dev/null -sS -w '%{time_total}' --max-time 10 "$URL" 2>/dev/null || echo 99)

HPA_EXISTS=False
kubectl get hpa -n "$NAMESPACE" --no-headers 2>/dev/null | grep -q . && HPA_EXISTS=True

PDB_EXISTS=False
kubectl get pdb "$DEPLOYMENT" -n "$NAMESPACE" >/dev/null 2>&1 && PDB_EXISTS=True

ES_READY=$(kubectl get externalsecret flask-runtime-secrets -n "$NAMESPACE" \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null || echo False)

ARGO_SYNC=$(kubectl get application "$ARGO_APP" -n argocd \
  -o jsonpath='{.status.sync.status}' 2>/dev/null || echo unknown)
ARGO_HEALTH=$(kubectl get application "$ARGO_APP" -n argocd \
  -o jsonpath='{.status.health.status}' 2>/dev/null || echo unknown)

DEPLOY_YAML=$(kubectl get deployment "$DEPLOYMENT" -n "$NAMESPACE" -o yaml 2>/dev/null || True)

RUN_AS_NON_ROOT=False
grep -q 'runAsNonRoot: True' <<<"$DEPLOY_YAML" && RUN_AS_NON_ROOT=True

NO_PRIV_ESC=False
grep -q 'allowPrivilegeEscalation: False' <<<"$DEPLOY_YAML" && NO_PRIV_ESC=True

SECCOMP=False
grep -q 'type: RuntimeDefault' <<<"$DEPLOY_YAML" && SECCOMP=True

STARTUP_PROBE=False
grep -q 'startupProbe:' <<<"$DEPLOY_YAML" && STARTUP_PROBE=True

TOPOLOGY_SPREAD=False
grep -q 'topologySpreadConstraints:' <<<"$DEPLOY_YAML" && TOPOLOGY_SPREAD=True

METRICS_API=False
kubectl top pods -n "$NAMESPACE" >/dev/null 2>&1 && METRICS_API=True

SERVICEMONITOR=False
kubectl get servicemonitor -n "$NAMESPACE" --no-headers 2>/dev/null | grep -q . && SERVICEMONITOR=True

GIT_REV=$(git rev-parse --short HEAD)
GIT_BRANCH=$(git branch --show-current)
GIT_CLEAN=False
[[ -z "$(git status --porcelain)" ]] && GIT_CLEAN=True

LAST_COMMIT_DATE=$(git log -1 --format=%cI)
LAST_COMMIT_MESSAGE=$(git log -1 --format=%s | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read().strip()))')

python3 - <<PY
import json
from datetime import datetime, timezone

data = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "platform": {
        "kubernetes_api": $KUBE_API,
        "nodes_ready": int("${NODE_READY:-0}"),
        "nodes_total": int("${NODE_TOTAL:-0}")
    },
    "workload": {
        "ready_replicas": int("${READY:-0}"),
        "desired_replicas": int("${DESIRED:-0}"),
        "container_restarts": int("${RESTARTS:-0}")
    },
    "networking": {
        "service_type": "${SERVICE_TYPE}",
        "ingress_exists": $INGRESS_EXISTS,
        "network_policy_count": int("${NETWORK_POLICIES:-0}")
    },
    "availability": {
        "http_code": "${HTTP_CODE}",
        "health_latency_seconds": float("${LATENCY}")
    },
    "resilience": {
        "hpa_exists": $HPA_EXISTS,
        "pdb_exists": $PDB_EXISTS,
        "startup_probe": $STARTUP_PROBE,
        "topology_spread": $TOPOLOGY_SPREAD
    },
    "identity": {
        "external_secret_ready": ${ES_READY^}
    },
    "gitops": {
        "sync_status": "${ARGO_SYNC}",
        "health_status": "${ARGO_HEALTH}"
    },
    "security": {
        "run_as_non_root": $RUN_AS_NON_ROOT,
        "privilege_escalation_disabled": $NO_PRIV_ESC,
        "seccomp_runtime_default": $SECCOMP
    },
    "observability": {
        "metrics_api_available": $METRICS_API,
        "service_monitor_present": $SERVICEMONITOR
    },
    "git": {
        "branch": "${GIT_BRANCH}",
        "revision": "${GIT_REV}",
        "clean": $GIT_CLEAN,
        "last_commit_date": "${LAST_COMMIT_DATE}",
        "last_commit_message": $LAST_COMMIT_MESSAGE
    }
}

checks = []

def add(area, name, ok, detail, warn=False):
    status = "PASS" if ok else ("WARN" if warn else "FAIL")
    checks.append({"area": area, "name": name, "status": status, "detail": detail})

add("Platform", "Kubernetes API", data["platform"]["kubernetes_api"], "Reachable" if data["platform"]["kubernetes_api"] else "Unreachable")
add("AKS", "Node readiness", data["platform"]["nodes_ready"] == data["platform"]["nodes_total"] and data["platform"]["nodes_total"] > 0,
    f'{data["platform"]["nodes_ready"]}/{data["platform"]["nodes_total"]} Ready')
add("Workload", "Deployment readiness", data["workload"]["ready_replicas"] == data["workload"]["desired_replicas"] and data["workload"]["desired_replicas"] > 0,
    f'{data["workload"]["ready_replicas"]}/{data["workload"]["desired_replicas"]} Ready')
add("Workload", "Container restarts", data["workload"]["container_restarts"] == 0,
    f'{data["workload"]["container_restarts"]} restarts', warn=True)
add("Networking", "Service exposure", data["networking"]["service_type"] == "ClusterIP",
    data["networking"]["service_type"], warn=True)
add("Networking", "Ingress", data["networking"]["ingress_exists"], "Configured" if data["networking"]["ingress_exists"] else "Missing")
add("Networking", "Network policies", data["networking"]["network_policy_count"] > 0,
    f'{data["networking"]["network_policy_count"]} policies')
add("Availability", "Public health", data["availability"]["http_code"] == "200",
    f'HTTP {data["availability"]["http_code"]}')
add("Performance", "Health latency", data["availability"]["health_latency_seconds"] < 0.5,
    f'{data["availability"]["health_latency_seconds"]:.3f}s', warn=True)
add("Resilience", "Horizontal autoscaling", data["resilience"]["hpa_exists"], "Configured", warn=True)
add("Resilience", "Pod disruption budget", data["resilience"]["pdb_exists"], "Configured", warn=True)
add("Resilience", "Startup probe", data["resilience"]["startup_probe"], "Configured", warn=True)
add("Scheduling", "Topology spread", data["resilience"]["topology_spread"], "Configured", warn=True)
add("Identity", "External Secret", data["identity"]["external_secret_ready"], "Ready", warn=True)
add("GitOps", "Argo CD", data["gitops"]["sync_status"] == "Synced" and data["gitops"]["health_status"] == "Healthy",
    f'{data["gitops"]["sync_status"]} / {data["gitops"]["health_status"]}', warn=True)
add("Security", "Non-root execution", data["security"]["run_as_non_root"], "Enforced", warn=True)
add("Security", "Privilege escalation", data["security"]["privilege_escalation_disabled"], "Disabled", warn=True)
add("Security", "Seccomp", data["security"]["seccomp_runtime_default"], "RuntimeDefault", warn=True)
add("Observability", "Metrics API", data["observability"]["metrics_api_available"], "Available", warn=True)
add("Observability", "ServiceMonitor", data["observability"]["service_monitor_present"], "Present", warn=True)
add("Repository", "Working tree", data["git"]["clean"], "Clean" if data["git"]["clean"] else "Local changes", warn=True)

data["checks"] = checks
weights = {"PASS": 100, "WARN": 50, "FAIL": 0}
data["score"] = round(sum(weights[c["status"]] for c in checks) / len(checks))
data["summary"] = {
    "pass": sum(c["status"] == "PASS" for c in checks),
    "warn": sum(c["status"] == "WARN" for c in checks),
    "fail": sum(c["status"] == "FAIL" for c in checks)
}

with open("$OUT_FILE", "w") as f:
    json.dump(data, f, indent=2)

print("$OUT_FILE")
PY

echo "Sanitised platform JSON written to $OUT_FILE"
