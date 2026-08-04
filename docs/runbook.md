# Operational Runbook

```bash
export NAMESPACE=production
```

## Initial Health Check

```bash
kubectl get deployment,replicaset,pods,service,ingress -n "$NAMESPACE" -o wide
kubectl get endpointslice,hpa,pdb -n "$NAMESPACE"
kubectl get externalsecret,secretstore,networkpolicy -n "$NAMESPACE"
```

Expected: Deployment replicas Ready, Service endpoints populated, Ingress has an address, HPA has metrics, ExternalSecret is Ready, and Argo CD is Synced and Healthy.

## Deployment Not Ready

```bash
kubectl rollout status deployment/flask-web -n "$NAMESPACE" --timeout=5m
kubectl describe deployment flask-web -n "$NAMESPACE"
kubectl describe pod -n "$NAMESPACE" -l app=flask-web
kubectl get events -n "$NAMESPACE" --sort-by='.lastTimestamp' | tail -40
kubectl logs -n "$NAMESPACE" -l app=flask-web --all-containers=true --tail=200
```

Common causes: image pull failure, missing Secret, failed probe, insufficient resources or invalid configuration.

## ImagePullBackOff

```bash
kubectl get deployment flask-web -n "$NAMESPACE" \
  -o=jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'

kubectl describe pod -n "$NAMESPACE" -l app=flask-web
```

Confirm the tag exists in ACR and AKS has `AcrPull`. Correct the image tag in Git and let Argo CD reconcile.

## ExternalSecret Failure

```bash
kubectl describe externalsecret flask-runtime-secrets -n "$NAMESPACE"
kubectl describe secretstore azure-key-vault -n "$NAMESPACE"
kubectl get serviceaccount external-secrets-kv -n "$NAMESPACE" -o yaml
kubectl get secret flask-runtime-secrets -n "$NAMESPACE"
```

Likely causes: federated subject mismatch, wrong ServiceAccount annotation, missing Key Vault permission, wrong vault URL or wrong secret name.

Do not print the Secret value.

## Argo CD OutOfSync

```bash
kubectl describe application flask-web-production -n argocd
argocd app get flask-web-production
argocd app diff flask-web-production
grep -A4 '^image:' flask-app/values-production.yaml
kubectl get deployment flask-web -n "$NAMESPACE" \
  -o=jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
```

Recovery:

```bash
argocd app sync flask-web-production
argocd app wait flask-web-production --health --sync --timeout 300
```

## Ingress or TLS Failure

```bash
kubectl describe ingress flask-web-prod -n "$NAMESPACE"
kubectl get certificate,certificaterequest,challenge,order -A
kubectl get pods,service -n ingress-nginx
kubectl logs -n ingress-nginx deployment/ingress-nginx-controller --tail=200
dig +short traditionalstrength.co.uk
curl -Iv https://traditionalstrength.co.uk/
curl -fsS https://traditionalstrength.co.uk/health
```

## Service Has No Endpoints

```bash
kubectl get service flask-web-prod-flask-app -n "$NAMESPACE" -o yaml
kubectl get endpointslice -n "$NAMESPACE" -o yaml
kubectl get pods -n "$NAMESPACE" --show-labels
```

Confirm the selector is `app=flask-web`, probes pass and target port is 8090.

## HPA Does Not Scale

```bash
kubectl describe hpa -n "$NAMESPACE"
kubectl top pods -n "$NAMESPACE"
kubectl top nodes
kubectl get deployment metrics-server -n kube-system
```

Generate controlled load:

```bash
kubectl run load-generator \
  --rm -i --tty --restart=Never \
  --image=busybox:1.36 \
  -- /bin/sh -c '
    while true; do
      wget -q -O- \
      http://flask-web-prod-flask-app.production.svc.cluster.local/health \
      >/dev/null
    done
  '
```

Observe:

```bash
kubectl get hpa,pods -n "$NAMESPACE" -w
```

## Roll Back a Bad Release

First determine whether the migration was backward compatible. A failed migration prevents the new Deployment rollout, so normally no image rollback is needed: inspect the retained failed Job without exposing environment values, fix the migration in application-owned code, and promote a new immutable image. Do not automatically downgrade a database schema; Alembic downgrades and PostgreSQL point-in-time restores require a separately reviewed data-recovery decision.

For a bad web rollout with a compatible schema, revert the GitOps promotion commit:

```bash
git log --oneline -- flask-app/values-production.yaml
git revert <bad-promotion-commit>
git push github main
argocd app wait flask-web-production --health --sync --timeout 300
kubectl rollout status deployment/flask-web -n "$NAMESPACE" --timeout=5m
```

Emergency rollback:

```bash
kubectl rollout history deployment/flask-web -n "$NAMESPACE"
kubectl rollout undo deployment/flask-web -n "$NAMESPACE"
```

Then correct Git, because Argo CD may restore the Git version.

Treat `kubectl rollout undo` as temporary containment only. Argo CD self-healing will restore the image and replica settings declared on `main`; immediately revert or correct `flask-app/values-production.yaml` in Git and wait for reconciliation. If the scale-out overlay was enabled, revert that Git change as well. Never roll the image back across an incompatible schema change until the database owner has approved the recovery plan.

## Pod Failure Test

```bash
POD=$(kubectl get pods -n "$NAMESPACE" -l app=flask-web \
  -o=jsonpath='{.items[0].metadata.name}')

kubectl delete pod "$POD" -n "$NAMESPACE"
kubectl get pods -n "$NAMESPACE" -l app=flask-web -w
```

Availability check:

```bash
for i in $(seq 1 20); do
  date
  curl -fsS https://traditionalstrength.co.uk/health || echo "REQUEST FAILED"
  sleep 2
done
```

## Argo CD Self-Healing Test

```bash
kubectl scale deployment flask-web -n "$NAMESPACE" --replicas=3
kubectl get deployment flask-web -n "$NAMESPACE" -w
```

Argo CD should restore the replica count declared in Git, unless HPA is actively controlling replicas.

## NetworkPolicy Test

Allowed namespace:

```bash
kubectl run network-test \
  -n ingress-nginx \
  --rm -i --tty --restart=Never \
  --image=curlimages/curl \
  -- curl -fsS \
  http://flask-web-prod-flask-app.production.svc.cluster.local/health
```

Unapproved namespace:

```bash
kubectl create namespace network-test --dry-run=client -o yaml | kubectl apply -f -

kubectl run blocked-test \
  -n network-test \
  --rm -i --tty --restart=Never \
  --image=curlimages/curl \
  -- curl --connect-timeout 5 \
  http://flask-web-prod-flask-app.production.svc.cluster.local/health

kubectl delete namespace network-test
```

The second request should fail.

## Terraform Validation

```bash
terraform -chdir=infra fmt -check -recursive
terraform -chdir=infra init -backend=false
terraform -chdir=infra validate

terraform -chdir=infra/aks fmt -check -recursive
terraform -chdir=infra/aks init -backend=false
terraform -chdir=infra/aks validate
```

## Helm Validation

```bash
helm lint flask-app -f flask-app/values-production.yaml
helm template flask-web-prod flask-app \
  -f flask-app/values-production.yaml \
  > /tmp/flask-production.yaml
helm template flask-web-prod flask-app \
  -f flask-app/values-production.yaml \
  -f flask-app/values-scale-out.yaml \
  > /tmp/flask-production-scale-out.yaml
kubectl create --dry-run=client -f /tmp/flask-production.yaml >/dev/null
kubectl create --dry-run=client -f /tmp/flask-production-scale-out.yaml >/dev/null
```

## Evidence Collection

```bash
mkdir -p evidence

kubectl get deployment,replicaset,pods,service,ingress,hpa,pdb \
  -n "$NAMESPACE" -o wide \
  > evidence/production-resources.txt

kubectl get networkpolicy,externalsecret,secretstore \
  -n "$NAMESPACE" \
  > evidence/security-resources.txt

argocd app get flask-web-production \
  > evidence/argocd-application.txt
```

Never save tokens, secret values or Terraform state in evidence files.
