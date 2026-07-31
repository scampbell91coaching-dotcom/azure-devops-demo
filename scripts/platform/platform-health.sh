#!/usr/bin/env bash
set -uo pipefail
NAMESPACE="${NAMESPACE:-production}"
DEPLOYMENT="${DEPLOYMENT:-flask-web}"
ARGO_APP="${ARGO_APP:-flask-web-production}"
URL="${URL:-https://traditionalstrength.co.uk/health}"
PASS=0; WARN=0; FAIL=0
ok(){ echo "PASS  $1"; PASS=$((PASS+1)); }
warn(){ echo "WARN  $1"; WARN=$((WARN+1)); }
bad(){ echo "FAIL  $1"; FAIL=$((FAIL+1)); }

echo "Platform Health Report"
echo "======================"

kubectl cluster-info >/dev/null 2>&1 && ok "Kubernetes API reachable" || bad "Kubernetes API unreachable"

READY=$(kubectl get deploy "$DEPLOYMENT" -n "$NAMESPACE" -o jsonpath='{.status.readyReplicas}' 2>/dev/null || true)
DESIRED=$(kubectl get deploy "$DEPLOYMENT" -n "$NAMESPACE" -o jsonpath='{.spec.replicas}' 2>/dev/null || true)
[[ -n "$READY" && "$READY" == "$DESIRED" ]] && ok "Deployment ready: $READY/$DESIRED" || bad "Deployment not fully ready: ${READY:-0}/${DESIRED:-unknown}"

TYPE=$(kubectl get svc flask-web-prod-flask-app -n "$NAMESPACE" -o jsonpath='{.spec.type}' 2>/dev/null || true)
[[ "$TYPE" == "ClusterIP" ]] && ok "Application Service is ClusterIP" || warn "Application Service type is ${TYPE:-unknown}"

kubectl get ingress flask-web-prod -n "$NAMESPACE" >/dev/null 2>&1 && ok "Ingress exists" || bad "Ingress missing"
curl -fsS --max-time 10 "$URL" >/dev/null 2>&1 && ok "Public health endpoint reachable" || bad "Public health endpoint failed"
kubectl get hpa -n "$NAMESPACE" --no-headers 2>/dev/null | grep -q . && ok "HPA present" || warn "HPA missing"
kubectl get pdb flask-web -n "$NAMESPACE" >/dev/null 2>&1 && ok "PDB present" || warn "PDB missing"
kubectl get networkpolicy -n "$NAMESPACE" --no-headers 2>/dev/null | grep -q . && ok "NetworkPolicies present" || bad "NetworkPolicies missing"

ES=$(kubectl get externalsecret flask-runtime-secrets -n "$NAMESPACE" -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null || true)
[[ "$ES" == "True" ]] && ok "ExternalSecret ready" || warn "ExternalSecret not Ready"

SYNC=$(kubectl get application "$ARGO_APP" -n argocd -o jsonpath='{.status.sync.status}' 2>/dev/null || true)
HEALTH=$(kubectl get application "$ARGO_APP" -n argocd -o jsonpath='{.status.health.status}' 2>/dev/null || true)
[[ "$SYNC" == "Synced" && "$HEALTH" == "Healthy" ]] && ok "Argo CD synced and healthy" || warn "Argo CD sync=$SYNC health=$HEALTH"

YAML=$(kubectl get deploy "$DEPLOYMENT" -n "$NAMESPACE" -o yaml 2>/dev/null || true)
grep -q 'runAsNonRoot: true' <<<"$YAML" && ok "runAsNonRoot enforced" || warn "runAsNonRoot missing"
grep -q 'allowPrivilegeEscalation: false' <<<"$YAML" && ok "Privilege escalation disabled" || warn "Privilege escalation control missing"
grep -q 'type: RuntimeDefault' <<<"$YAML" && ok "RuntimeDefault seccomp enabled" || warn "RuntimeDefault seccomp missing"
grep -q 'startupProbe:' <<<"$YAML" && ok "Startup probe configured" || warn "Startup probe missing"
grep -q 'topologySpreadConstraints:' <<<"$YAML" && ok "Topology spread configured" || warn "Topology spread missing"

TOTAL=$((PASS+WARN+FAIL))
SCORE=$(( TOTAL > 0 ? (PASS*100 + WARN*50)/TOTAL : 0 ))
echo
echo "PASS=$PASS WARN=$WARN FAIL=$FAIL SCORE=${SCORE}%"
(( FAIL == 0 ))
