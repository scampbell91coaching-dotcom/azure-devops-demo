# Private Platform Source Manifests

These files preserve the working private portal, oauth2-proxy, ingress buffer settings, TLS routing and NetworkPolicies.

`platform-portal-private` is the authenticated Flask coaching application behind
OAuth2 Proxy. Its image is promoted independently from the public `flask-web`
Helm release. Before each private rollout, an init container applies additive
Alembic migrations, imports the bundled 276-exercise catalogue idempotently,
and verifies PostgreSQL without logging the connection string. Existing rows
without a catalogue version are coach-maintained and are never overwritten.

The Secret `platform-oauth2-proxy` is intentionally excluded from Git. It must contain:

- `client-secret`
- `cookie-secret`

Apply with:

```bash
kubectl apply -f private-platform-manifests/
```

Safe live verification (does not display secret values):

```bash
az aks command invoke --resource-group "$AKS_RESOURCE_GROUP" --name "$AKS_CLUSTER_NAME" --command '
  kubectl -n production get ingress platform-portal-private -o jsonpath="{.spec.rules[*].host}{\"\\n\"}";
  kubectl -n production get deploy platform-portal-private -o jsonpath="{.spec.template.spec.containers[?(@.name==\"portal\")].image}{\"\\n\"}";
  kubectl -n production exec deploy/platform-portal-private -c portal -- flask verify-production-db
'
```
