# Private Platform Source Manifests

These files preserve the working private portal, oauth2-proxy, ingress buffer settings, TLS routing and NetworkPolicies.

`platform-portal-private` is the authenticated Flask coaching application behind
OAuth2 Proxy. Its image is promoted independently from the public `flask-web`
Helm release. Before each private rollout, an Argo CD PreSync Job applies additive
Alembic migrations, imports the bundled 276-exercise catalogue idempotently,
and verifies PostgreSQL without logging the connection string. Existing rows
without a catalogue version are coach-maintained and are never overwritten.

The portal container reads `DATABASE_URL` only from `flask-runtime-secrets`
(Key Vault `database-runtime-url`). The PreSync Job reads it only from
`flask-migration-secrets` (Key Vault `database-url`). Keeping migration work in
a separate Pod prevents the privileged database credential from being attached
to the long-lived portal Pod.

The Secret `platform-oauth2-proxy` is intentionally excluded from Git. It must contain:

- `client-secret`
- `cookie-secret`

## Platform status snapshots

`platform-status-collector` runs every five minutes, reads only the production
workload resources, cluster node readiness, the named Argo CD Application, and
the metrics/ServiceMonitor APIs, then atomically replaces
`/status/platform-status.json`. A dedicated `azurefile-csi` ReadWriteMany PVC is
used because the short-lived writer and portal reader may run on different
nodes. The portal mounts that claim read-only and explicitly sets
`PLATFORM_STATUS_FILE`; it has no Kubernetes API token.

The collector RBAC has only `get`/`list`: pods and services, the named
deployment and ingress-related resources in `production`; node list; pod
metrics and ServiceMonitors; and `get` for the single
`flask-web-production` Argo Application. It has no create, patch, update,
delete, secrets, logs, exec, or events permissions. Collection jobs time out
after two minutes and never overlap. A snapshot is current for 15 minutes;
older data is stale, a configured but unreadable snapshot is unavailable, and
an unset `PLATFORM_STATUS_FILE` is not configured.

Infrastructure prerequisite: the AKS cluster must provide the built-in
`azurefile-csi` StorageClass and permit dynamic ReadWriteMany provisioning.

For deterministic local UI/API checks (the values are synthetic fixtures):

```bash
cd platform-portal
python -m portal.collectors.platform_status --sample --output /tmp/platform-status.json
PLATFORM_STATUS_FILE=/tmp/platform-status.json \
PLATFORM_STATUS_FRESHNESS_SECONDS=900 flask run
```

Use `--sample-state stale` to generate a snapshot just beyond the configured
threshold. Point `PLATFORM_STATUS_FILE` at a nonexistent path for the
configured-but-missing/unavailable state, or leave it unset for not configured.

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
