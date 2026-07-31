#!/usr/bin/env bash
set -euo pipefail

REPO="${1:-$HOME/azure-devops-demo}"
NAMESPACE="${NAMESPACE:-production}"
DEPLOYMENT="${DEPLOYMENT:-flask-web}"
SERVICE="${SERVICE:-flask-web-prod-flask-app}"
INGRESS="${INGRESS:-flask-web-prod}"
ARGO_APP="${ARGO_APP:-flask-web-production}"
URL="${URL:-https://traditionalstrength.co.uk/health}"
OUT_DIR="${OUT_DIR:-$REPO/dashboard}"
OUT_FILE="$OUT_DIR/index.html"

cd "$REPO"
mkdir -p "$OUT_DIR"

status_class() {
  case "$1" in
    PASS) echo "pass" ;;
    WARN) echo "warn" ;;
    *) echo "fail" ;;
  esac
}

PASS=0
WARN=0
FAIL=0
ROWS=""

add_check() {
  local area="$1"
  local check="$2"
  local status="$3"
  local detail="$4"

  case "$status" in
    PASS) PASS=$((PASS+1)) ;;
    WARN) WARN=$((WARN+1)) ;;
    FAIL) FAIL=$((FAIL+1)) ;;
  esac

  local cls
  cls="$(status_class "$status")"

  ROWS+="<tr><td>${area}</td><td>${check}</td><td><span class=\"badge ${cls}\">${status}</span></td><td>${detail}</td></tr>"
}

# Kubernetes API
if kubectl cluster-info >/dev/null 2>&1; then
  add_check "Platform" "Kubernetes API" "PASS" "Reachable"
else
  add_check "Platform" "Kubernetes API" "FAIL" "Unreachable"
fi

# Nodes (counts only, no names/IPs)
NODE_TOTAL=$(kubectl get nodes --no-headers 2>/dev/null | wc -l | tr -d ' ')
NODE_READY=$(kubectl get nodes --no-headers 2>/dev/null | awk '$2=="Ready"{c++} END{print c+0}')
if [[ "$NODE_TOTAL" -gt 0 && "$NODE_TOTAL" == "$NODE_READY" ]]; then
  add_check "AKS" "Node readiness" "PASS" "$NODE_READY/$NODE_TOTAL Ready"
else
  add_check "AKS" "Node readiness" "FAIL" "$NODE_READY/$NODE_TOTAL Ready"
fi

# Workload readiness
READY=$(kubectl get deploy "$DEPLOYMENT" -n "$NAMESPACE" -o jsonpath='{.status.readyReplicas}' 2>/dev/null || true)
DESIRED=$(kubectl get deploy "$DEPLOYMENT" -n "$NAMESPACE" -o jsonpath='{.spec.replicas}' 2>/dev/null || true)
if [[ -n "$READY" && "$READY" == "$DESIRED" ]]; then
  add_check "Workload" "Deployment readiness" "PASS" "$READY/$DESIRED replicas Ready"
else
  add_check "Workload" "Deployment readiness" "FAIL" "${READY:-0}/${DESIRED:-unknown} replicas Ready"
fi

RESTARTS=$(kubectl get pods -n "$NAMESPACE" -l app=flask-web \
  -o jsonpath='{range .items[*]}{range .status.containerStatuses[*]}{.restartCount}{"\n"}{end}{end}' 2>/dev/null \
  | awk '{s+=$1} END{print s+0}')
if [[ "$RESTARTS" -eq 0 ]]; then
  add_check "Workload" "Container restarts" "PASS" "0 restarts"
else
  add_check "Workload" "Container restarts" "WARN" "$RESTARTS restarts"
fi

# Service/Ingress
SERVICE_TYPE=$(kubectl get svc "$SERVICE" -n "$NAMESPACE" -o jsonpath='{.spec.type}' 2>/dev/null || true)
if [[ "$SERVICE_TYPE" == "ClusterIP" ]]; then
  add_check "Networking" "Application Service" "PASS" "ClusterIP behind ingress"
else
  add_check "Networking" "Application Service" "WARN" "Service type: ${SERVICE_TYPE:-unknown}"
fi

if kubectl get ingress "$INGRESS" -n "$NAMESPACE" >/dev/null 2>&1; then
  add_check "Networking" "Ingress" "PASS" "Configured"
else
  add_check "Networking" "Ingress" "FAIL" "Missing"
fi

NP_COUNT=$(kubectl get networkpolicy -n "$NAMESPACE" --no-headers 2>/dev/null | wc -l | tr -d ' ')
if [[ "$NP_COUNT" -gt 0 ]]; then
  add_check "Networking" "Network policies" "PASS" "$NP_COUNT policies"
else
  add_check "Networking" "Network policies" "FAIL" "No policies"
fi

# Public health and latency
HTTP_CODE=$(curl -o /dev/null -sS -w '%{http_code}' --max-time 10 "$URL" 2>/dev/null || echo 000)
LATENCY=$(curl -o /dev/null -sS -w '%{time_total}' --max-time 10 "$URL" 2>/dev/null || echo 99)

if [[ "$HTTP_CODE" == "200" ]]; then
  add_check "Availability" "Public health endpoint" "PASS" "HTTP 200"
else
  add_check "Availability" "Public health endpoint" "FAIL" "HTTP $HTTP_CODE"
fi

if awk -v t="$LATENCY" 'BEGIN{exit !(t < 0.5)}'; then
  add_check "Performance" "Health latency" "PASS" "${LATENCY}s"
elif awk -v t="$LATENCY" 'BEGIN{exit !(t < 1.0)}'; then
  add_check "Performance" "Health latency" "WARN" "${LATENCY}s"
else
  add_check "Performance" "Health latency" "FAIL" "${LATENCY}s"
fi

# Autoscaling / resilience
if kubectl get hpa -n "$NAMESPACE" --no-headers 2>/dev/null | grep -q .; then
  add_check "Resilience" "Horizontal autoscaling" "PASS" "Configured"
else
  add_check "Resilience" "Horizontal autoscaling" "WARN" "Not found"
fi

if kubectl get pdb "$DEPLOYMENT" -n "$NAMESPACE" >/dev/null 2>&1; then
  add_check "Resilience" "Pod disruption budget" "PASS" "Configured"
else
  add_check "Resilience" "Pod disruption budget" "WARN" "Not found"
fi

# External Secrets
ES_READY=$(kubectl get externalsecret flask-runtime-secrets -n "$NAMESPACE" \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null || true)
if [[ "$ES_READY" == "True" ]]; then
  add_check "Identity" "External Secret" "PASS" "Ready"
else
  add_check "Identity" "External Secret" "WARN" "Not Ready"
fi

# Argo CD
ARGO_SYNC=$(kubectl get application "$ARGO_APP" -n argocd -o jsonpath='{.status.sync.status}' 2>/dev/null || true)
ARGO_HEALTH=$(kubectl get application "$ARGO_APP" -n argocd -o jsonpath='{.status.health.status}' 2>/dev/null || true)
if [[ "$ARGO_SYNC" == "Synced" && "$ARGO_HEALTH" == "Healthy" ]]; then
  add_check "GitOps" "Argo CD" "PASS" "Synced and Healthy"
else
  add_check "GitOps" "Argo CD" "WARN" "Sync=${ARGO_SYNC:-unknown}, Health=${ARGO_HEALTH:-unknown}"
fi

# Runtime security controls
DEPLOY_YAML=$(kubectl get deploy "$DEPLOYMENT" -n "$NAMESPACE" -o yaml 2>/dev/null || true)

if grep -q 'runAsNonRoot: true' <<<"$DEPLOY_YAML"; then
  add_check "Security" "Non-root execution" "PASS" "Enforced"
else
  add_check "Security" "Non-root execution" "WARN" "Not detected"
fi

if grep -q 'allowPrivilegeEscalation: false' <<<"$DEPLOY_YAML"; then
  add_check "Security" "Privilege escalation" "PASS" "Disabled"
else
  add_check "Security" "Privilege escalation" "WARN" "Not detected"
fi

if grep -q 'type: RuntimeDefault' <<<"$DEPLOY_YAML"; then
  add_check "Security" "Seccomp" "PASS" "RuntimeDefault"
else
  add_check "Security" "Seccomp" "WARN" "Not detected"
fi

if grep -q 'startupProbe:' <<<"$DEPLOY_YAML"; then
  add_check "Reliability" "Startup probe" "PASS" "Configured"
else
  add_check "Reliability" "Startup probe" "WARN" "Missing"
fi

if grep -q 'topologySpreadConstraints:' <<<"$DEPLOY_YAML"; then
  add_check "Scheduling" "Topology spread" "PASS" "Configured"
else
  add_check "Scheduling" "Topology spread" "WARN" "Missing"
fi

# Git / desired state
GIT_REV=$(git rev-parse --short HEAD)
GIT_BRANCH=$(git branch --show-current)
if [[ -z "$(git status --porcelain)" ]]; then
  add_check "Repository" "Working tree" "PASS" "Clean"
else
  add_check "Repository" "Working tree" "WARN" "Local changes present"
fi

TOTAL=$((PASS+WARN+FAIL))
SCORE=$(( TOTAL > 0 ? (PASS*100 + WARN*50)/TOTAL : 0 ))
STAMP=$(date -Is)

cat > "$OUT_FILE" <<EOF
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Azure Platform Dashboard</title>
<style>
:root{
  --bg:#0b1220;
  --panel:#111a2e;
  --panel2:#17223a;
  --text:#e8eef8;
  --muted:#9fb0c8;
  --border:#263653;
  --accent:#5da9ff;
  --pass:#4ade80;
  --warn:#facc15;
  --fail:#fb7185;
}
*{box-sizing:border-box}
body{
  margin:0;
  font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  background:var(--bg);
  color:var(--text);
}
main{
  max-width:1180px;
  margin:0 auto;
  padding:28px 20px 60px;
}
header{
  display:flex;
  flex-wrap:wrap;
  justify-content:space-between;
  gap:18px;
  align-items:end;
  margin-bottom:24px;
}
h1{margin:0;font-size:2rem}
.sub{color:var(--muted);margin-top:6px}
.grid{
  display:grid;
  grid-template-columns:repeat(4,minmax(0,1fr));
  gap:14px;
  margin-bottom:20px;
}
.card{
  background:var(--panel);
  border:1px solid var(--border);
  border-radius:14px;
  padding:18px;
}
.label{color:var(--muted);font-size:.85rem}
.value{font-size:2rem;font-weight:700;margin-top:6px}
.score{color:var(--accent)}
.pass-text{color:var(--pass)}
.warn-text{color:var(--warn)}
.fail-text{color:var(--fail)}
.table-wrap{
  overflow:auto;
  background:var(--panel);
  border:1px solid var(--border);
  border-radius:14px;
}
table{width:100%;border-collapse:collapse;min-width:760px}
th,td{padding:13px 14px;text-align:left;border-bottom:1px solid var(--border)}
th{color:var(--muted);font-weight:600;background:var(--panel2)}
tr:last-child td{border-bottom:none}
.badge{
  display:inline-block;
  border-radius:999px;
  padding:4px 9px;
  font-size:.75rem;
  font-weight:700;
}
.badge.pass{color:var(--pass);background:rgba(74,222,128,.12)}
.badge.warn{color:var(--warn);background:rgba(250,204,21,.12)}
.badge.fail{color:var(--fail);background:rgba(251,113,133,.12)}
.footer{
  color:var(--muted);
  margin-top:18px;
  font-size:.9rem;
}
.note{
  margin:18px 0;
  padding:14px 16px;
  background:var(--panel2);
  border-left:4px solid var(--accent);
  border-radius:8px;
  color:var(--muted);
}
@media(max-width:760px){
  .grid{grid-template-columns:repeat(2,minmax(0,1fr))}
}
</style>
</head>
<body>
<main>
<header>
  <div>
    <h1>Azure Platform Dashboard</h1>
    <div class="sub">Sanitised operational summary for the AKS platform</div>
  </div>
  <div class="sub">Generated $STAMP</div>
</header>

<section class="grid">
  <div class="card">
    <div class="label">Platform score</div>
    <div class="value score">${SCORE}%</div>
  </div>
  <div class="card">
    <div class="label">Passing checks</div>
    <div class="value pass-text">$PASS</div>
  </div>
  <div class="card">
    <div class="label">Warnings</div>
    <div class="value warn-text">$WARN</div>
  </div>
  <div class="card">
    <div class="label">Failures</div>
    <div class="value fail-text">$FAIL</div>
  </div>
</section>

<div class="note">
  This dashboard intentionally excludes IP addresses, node names, secret values, raw manifests, tenant IDs, client IDs, registry names and Key Vault names.
</div>

<section class="table-wrap">
<table>
<thead>
<tr>
  <th>Area</th>
  <th>Control</th>
  <th>Status</th>
  <th>Detail</th>
</tr>
</thead>
<tbody>
$ROWS
</tbody>
</table>
</section>

<div class="footer">
  Git branch: $GIT_BRANCH · Revision: $GIT_REV · Source: live Kubernetes checks and Git desired state
</div>
</main>
</body>
</html>
EOF

echo "Dashboard generated: $OUT_FILE"
echo "Score: $SCORE% | PASS=$PASS WARN=$WARN FAIL=$FAIL"
