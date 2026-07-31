#!/usr/bin/env bash
set -euo pipefail
REPO="${1:-$HOME/azure-devops-demo}"
NAMESPACE="${NAMESPACE:-production}"
ARGO_APP="${ARGO_APP:-flask-web-production}"
cd "$REPO"

echo "=== Git ==="
git status --short
[[ -z "$(git status --porcelain)" ]] && echo "PASS: working tree clean" || echo "WARN: working tree dirty"

echo
echo "=== Argo CD ==="
kubectl get application "$ARGO_APP" -n argocd -o custom-columns=NAME:.metadata.name,SYNC:.status.sync.status,HEALTH:.status.health.status,REVISION:.status.sync.revision

helm template flask-web-prod flask-app -f flask-app/values-production.yaml >/tmp/flask-desired.yaml

echo
echo "=== Image ==="
GIT_TAG=$(awk '/^image:/{f=1;next} f&&/^[^ ]/{f=0} f&&$1=="tag:"{print $2;exit}' flask-app/values-production.yaml)
LIVE_IMAGE=$(kubectl get deploy flask-web -n "$NAMESPACE" -o jsonpath='{.spec.template.spec.containers[0].image}')
echo "Git tag: $GIT_TAG"
echo "Live:    $LIVE_IMAGE"
[[ "$LIVE_IMAGE" == *":$GIT_TAG" ]] && echo "PASS: image matches" || echo "WARN: image differs"

echo
echo "=== Service type ==="
DESIRED=$(grep -A20 '^kind: Service$' /tmp/flask-desired.yaml | awk '$1=="type:"{print $2;exit}')
LIVE=$(kubectl get svc flask-web-prod-flask-app -n "$NAMESPACE" -o jsonpath='{.spec.type}')
echo "Desired: $DESIRED"
echo "Live:    $LIVE"
[[ "$DESIRED" == "$LIVE" ]] && echo "PASS: service type matches" || echo "WARN: service type differs"
