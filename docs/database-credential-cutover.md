# Production database credential cutover

This runbook separates PostgreSQL credentials without storing or displaying a
connection string. The names below are identifiers only.

## Preconditions

- Key Vault contains `database-runtime-url` for the restricted `ts_runtime`
  login and `database-url` for migrations.
- The runtime login has already passed connect/read and DDL/role/database denial
  checks.
- External Secrets and Azure Workload Identity are healthy.
- The reviewed Git commit contains the two-Secret configuration and immutable
  application image references.

## Cutover

1. Merge through the normal reviewed GitOps path. Do not manually create a
   credential-bearing Kubernetes Secret or pass a URL through Helm values.
2. Confirm External Secrets reports Ready for `flask-runtime-secrets` and
   `flask-migration-secrets`. Check key names and conditions only; do not read or
   decode Secret data.
3. Sync the `external-secrets-production` Argo CD application before either
   application. Confirm both
   target Secrets exist and contain a `DATABASE_URL` key using key-name-only
   inspection.
4. Sync `flask-web-production`. Its Helm pre-upgrade migration Job must complete
   before the Deployment rolls. Confirm the Job references
   `flask-migration-secrets` and the Deployment references only
   `flask-runtime-secrets`.
5. Sync `platform-portal-private`. Its Argo CD PreSync migration Job must
   complete before the portal Deployment. Confirm the Job and Deployment use
   the migration and runtime Secrets respectively.
6. Verify rollout health, public and authenticated health endpoints, a
   representative application read/write, and migration status. Inspect pod
   specifications and logs for secret *names* only; never output environment
   values.
7. Re-run the runtime denial checks from an approved ephemeral test mechanism.

## Rollback

1. Stop further application syncs if either migration fails. A failed PreSync or
   Helm hook leaves the existing runtime Deployment serving the previous image.
2. Roll back application image/configuration to the last reviewed Git revision.
   Prefer a forward fix for any schema already applied; do not attempt an
   unreviewed destructive database downgrade.
3. If the restricted role causes an application regression, revert the runtime
   Secret reference to the prior reviewed single-credential revision, sync it,
   and verify health. This is a time-boxed emergency rollback because it restores
   administrator access to runtime pods.
4. Confirm both Flask and private portal Deployments become healthy, then open a
   follow-up to restore separation before normal releases resume.

## Cleanup after successful validation

Delete these temporary Kubernetes resources only after the cutover, denial
checks, and rollback checkpoint are complete:

- `ts-runtime-bootstrap`
- `ts-runtime-handoff`
- `ts-runtime-test`
- `ts-runtime-denial-test`

Resolve each resource's kind and namespace with a read-only query first. Delete
only those exact targets; do not use label-wide or namespace-wide deletion.
