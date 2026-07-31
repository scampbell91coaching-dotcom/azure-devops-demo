#!/usr/bin/env bash
set -euo pipefail
REPO="${1:-$HOME/azure-devops-demo}"
cd "$REPO"
PASS=0; FAIL=0
check(){ local n="$1"; shift; echo; echo "== $n =="; if "$@"; then echo "PASS: $n"; PASS=$((PASS+1)); else echo "FAIL: $n"; FAIL=$((FAIL+1)); fi; }

check "Git tree clean" bash -c 'test -z "$(git status --porcelain)"'
check "Terraform root fmt" terraform -chdir=infra fmt -check -recursive
check "Terraform root validate" terraform -chdir=infra validate
check "Terraform AKS fmt" terraform -chdir=infra/aks fmt -check -recursive
check "Terraform AKS validate" terraform -chdir=infra/aks validate
check "Helm lint" helm lint flask-app -f flask-app/values-production.yaml
check "Helm render" bash -c 'helm template flask-web-prod flask-app -f flask-app/values-production.yaml >/tmp/flask-production.yaml'
check "Kubernetes server dry-run" kubectl apply --dry-run=server -f /tmp/flask-production.yaml
check "No tracked Terraform state/plans" bash -c '! git ls-files | grep -Eq "(^|/)(terraform\.tfstate|terraform\.tfstate\.backup|.*\.tfplan)$"'
check "Service renders ClusterIP" bash -c 'grep -q "type: ClusterIP" /tmp/flask-production.yaml'
check "Runtime security renders" bash -c 'grep -q "allowPrivilegeEscalation: false" /tmp/flask-production.yaml && grep -q "runAsNonRoot: true" /tmp/flask-production.yaml'
check "Startup probe renders" bash -c 'grep -q "startupProbe:" /tmp/flask-production.yaml'
check "Topology spread renders" bash -c 'grep -q "topologySpreadConstraints:" /tmp/flask-production.yaml'

echo
echo "PASS=$PASS FAIL=$FAIL"
(( FAIL == 0 ))
