#!/usr/bin/env bash
set -uo pipefail

NAMESPACE="${NAMESPACE:-production}"
DEPLOYMENT="${DEPLOYMENT:-flask-web}"
SERVICE="${SERVICE:-flask-web-prod-flask-app}"
INGRESS="${INGRESS:-flask-web-prod}"
ARGO_APP="${ARGO_APP:-flask-web-production}"
URL="${URL:-https://traditionalstrength.co.uk/health}"

PASS=0
WARN=0
FAIL=0

ok() {
  printf 'PASS  %s\n' "$1"
  PASS=$((PASS + 1))
}

warn() {
  printf 'WARN  %s\n' "$1"
  WARN=$((WARN + 1))
}

bad() {
  printf 'FAIL  %s\n' "$1"
  FAIL=$((FAIL + 1))
}

printf '\nPlatform Health Report\n'
printf '======================\n\n'

if kubectl cluster-info >/dev/null 2>&1; then
  ok "Kubernetes API reachable"
else
  bad "Kubernetes API unreachable"
fi

READY="$(
  kubectl get deploy "$DEPLOYMENT" \
    -n "$NAMESPACE" \
    -o jsonpath='{.status.readyReplicas}' \
    2>/dev/null || true
)"

DESIRED="$(
  kubectl get deploy "$DEPLOYMENT" \
    -n "$NAMESPACE" \
    -o jsonpath='{.spec.replicas}' \
    2>/dev/null || true
)"

if [[ -n "$READY" && "$READY" == "$DESIRED" ]]; then
  ok "Deployment ready: $READY/$DESIRED"
else
  bad "Deployment not fully ready: ${READY:-0}/${DESIRED:-unknown}"
fi

TYPE="$(
  kubectl get svc "$SERVICE" \
    -n "$NAMESPACE" \
    -o jsonpath='{.spec.type}' \
    2>/dev/null || true
)"

if [[ "$TYPE" == "ClusterIP" ]]; then
  ok "Application Service is ClusterIP"
else
  warn "Application Service type is ${TYPE:-unknown}"
fi

if kubectl get ingress "$INGRESS" -n "$NAMESPACE" >/dev/null 2>&1; then
  ok "Ingress exists"
else
  bad "Ingress missing"
fi

if curl -fsS --max-time 10 "$URL" >/dev/null 2>&1; then
  ok "Public health endpoint reachable"
else
  bad "Public health endpoint failed"
fi

if kubectl get hpa -n "$NAMESPACE" --no-headers 2>/dev/null | grep -q .; then
  ok "HPA present"
else
  warn "HPA missing"
fi

if kubectl get pdb "$DEPLOYMENT" -n "$NAMESPACE" >/dev/null 2>&1; then
  ok "PDB present"
else
  warn "PDB missing"
fi

if kubectl get networkpolicy -n "$NAMESPACE" --no-headers 2>/dev/null | grep -q .; then
  ok "NetworkPolicies present"
else
  bad "NetworkPolicies missing"
fi

ES="$(
  kubectl get externalsecret flask-runtime-secrets \
    -n "$NAMESPACE" \
    -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' \
    2>/dev/null || true
)"

if [[ "$ES" == "True" ]]; then
  ok "ExternalSecret ready"
else
  warn "ExternalSecret not Ready"
fi

SYNC="$(
  kubectl get application "$ARGO_APP" \
    -n argocd \
    -o jsonpath='{.status.sync.status}' \
    2>/dev/null || true
)"

HEALTH="$(
  kubectl get application "$ARGO_APP" \
    -n argocd \
    -o jsonpath='{.status.health.status}' \
    2>/dev/null || true
)"

if [[ "$SYNC" == "Synced" && "$HEALTH" == "Healthy" ]]; then
  ok "Argo CD synced and healthy"
else
  warn "Argo CD sync=${SYNC:-unknown} health=${HEALTH:-unknown}"
fi

YAML="$(
  kubectl get deploy "$DEPLOYMENT" \
    -n "$NAMESPACE" \
    -o yaml \
    2>/dev/null || true
)"

if grep -q 'runAsNonRoot: true' <<<"$YAML"; then
  ok "runAsNonRoot enforced"
else
  warn "runAsNonRoot missing"
fi

if grep -q 'allowPrivilegeEscalation: false' <<<"$YAML"; then
  ok "Privilege escalation disabled"
else
  warn "Privilege escalation control missing"
fi

if grep -q 'type: RuntimeDefault' <<<"$YAML"; then
  ok "RuntimeDefault seccomp enabled"
else
  warn "RuntimeDefault seccomp missing"
fi

if grep -q 'startupProbe:' <<<"$YAML"; then
  ok "Startup probe configured"
else
  warn "Startup probe missing"
fi

if grep -q 'topologySpreadConstraints:' <<<"$YAML"; then
  ok "Topology spread configured"
else
  warn "Topology spread missing"
fi

TOTAL=$((PASS + WARN + FAIL))

if ((TOTAL > 0)); then
  SCORE=$(((PASS * 100 + WARN * 50) / TOTAL))
else
  SCORE=0
fi

printf '\nSummary\n'
printf '=======\n'
printf 'PASS: %d\n' "$PASS"
printf 'WARN: %d\n' "$WARN"
printf 'FAIL: %d\n' "$FAIL"
printf 'Score: %d%%\n' "$SCORE"

if ((FAIL > 0)); then
  exit 1
fi
