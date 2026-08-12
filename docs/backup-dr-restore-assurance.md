# Backup, disaster recovery, and restore assurance

This is the production-safe assurance baseline for the paid Traditional Strength powerlifting service. It records repository evidence and defines an operator rehearsal; it does not assert that a live backup was inspected or restored. Never use the commands below against the source server, and never put credentials or athlete data in evidence.

## Current-state inventory

| Surface | Repository evidence | Assurance conclusion |
| --- | --- | --- |
| PostgreSQL | `infra/environments/dev/terraform.tfvars` selects seven-day retention, no geo-redundant backup, and no HA. `infra/modules/postgresql/main.tf` uses Azure Flexible Server, private networking, TLS, storage auto-grow, and `prevent_destroy`. | Azure-managed PITR is declared, locally redundant and single-region. Configuration is not proof of backup freshness or restorability. |
| Restore | `docs/azure-postgresql.md` says PITR creates a new server and records an example Azure CLI command. | No automated restore and no recorded successful exercise exist. The source must never be restored over or repointed during a rehearsal. |
| Schema/release | Helm/Argo migration jobs run Alembic upgrade before rollout. The migration tree currently has one reviewed head. | A recovered database must have exactly one `alembic_version` row equal to the immutable application release's reviewed head. Do not upgrade a restore merely to make this check pass. |
| Durable application data | Deployed state is PostgreSQL; Redis sessions are disposable. Training prescriptions/results, coaching records, and meal-plan JSON snapshots are database records. | PostgreSQL recovery is the current application-data recovery boundary. Cache/session loss is expected and users may need to sign in again. |
| Files/PDFs | The product audits state that no generated meal-plan PDF/blob model, download route, or general-purpose application object store exists. | There are no meal-plan PDF objects to recover today. A future object store needs its own backup, inventory, and restore drill before PDF export ships. |
| Region | Geo-backup and HA are disabled. | A region-wide loss may exceed the targets below or be unrecoverable from managed backups. This is an explicitly accepted gap until geo recovery is funded and rehearsed. |

## Service objectives and escalation

For a small paid, supervised PL SaaS, adopt an **operational RPO of 15 minutes** for database incidents and an **RTO of 4 hours** for a recoverable server/database failure. The **regional-disaster objective is RPO 24 hours / RTO 24 hours only after** an independent geo-capable copy and regional restore have been implemented and tested; the present non-geo configuration cannot claim it. Keep seven days as the minimum recovery window, but raise retention or add a separately governed logical/archive copy if deletion discovery, commercial support, or legal needs exceed seven days.

Alert the service owner if the latest restorable point is older than 15 minutes, backup status is not healthy, retention is below seven days, or the quarterly rehearsal is overdue. Stop claiming the objective until evidence is restored. HA can reduce outage time but is not backup.

## Quarterly non-destructive rehearsal

Use a named operator, approver, incident/change ID, source resource ID, requested UTC restore point, and isolated destination name. Record start/end timestamps for measured RTO. The person executing Azure changes must follow the normal approval path; this repository does not authorize them.

1. Read-only preflight: record the source server resource ID, region, PostgreSQL version, backup retention/redundancy, earliest/latest restore times or backup timestamps, and provider health. Capture sanitized command output. Confirm the selected UTC restore point is within retention and at least five minutes before the exercise begins.
2. Create a **new**, uniquely named server from PITR using the approved Azure procedure in `docs/azure-postgresql.md`. Never choose the source name. Place it in an isolated recovery network/subscription/resource group as policy requires; deny application and public traffic. Do not alter production DNS, Key Vault secrets, Kubernetes secrets, GitOps, or traffic.
3. Create a temporary least-privilege verifier credential through the approved secret channel. Export it only in the operator's protected shell as `RESTORE_DATABASE_URL`; do not paste it into evidence. Determine the code head from the exact candidate/recovered release with `python -m alembic -c migrations/alembic.ini heads` in `platform-portal`; require exactly one line and review the revision.
4. Run the verifier against the disposable restore:

   ```bash
   RESTORE_DATABASE_URL='<secret URI for disposable restore>' \
     python scripts/backup_dr/restore_verify.py \
       --source-host '<source FQDN>' \
       --expected-head '<reviewed Alembic head>' \
       --rehearsal-id '<change-or-exercise-id>' \
       --confirm I_CONFIRM_THIS_IS_A_DISPOSABLE_RESTORE \
       > restore-verification.json
   ```

   The script rejects a target whose hostname equals the declared source, starts a read-only transaction, applies query/lock timeouts, checks one expected Alembic head, critical PL tables, and validated constraints, and emits no URI, hostname, row content, or row counts. Exit 0 is necessary but not sufficient.
5. In an isolated application deployment with outbound side effects disabled (email, billing, webhooks, jobs, and athlete access), verify login, coach athlete list, one representative programme/session, one training log, and one meal-plan assignment. Use designated synthetic canaries or aggregate expectations—never copy PII into evidence. Confirm the recovered canary's last-known timestamp brackets the requested restore point; this proves the effective RPO better than resource status alone.
6. Record measured restore duration, validation duration, total RTO, achieved restore point/RPO, exceptions, approver, and cleanup owner. Destroying the temporary server is a separate approved action after evidence acceptance and retention requirements; verify production references still point to the source first.

The verifier does not invoke `az`, create a server, run migrations, write canaries, change secrets, or clean up resources.

## Evidence required for a pass

Keep a sanitized evidence bundle with: exercise/change ID and approvals; source resource identity (no credentials); requested and provider-reported restore point; preflight backup status, retention, redundancy, freshness and capture time; destination resource identity and proof it differs from source; PostgreSQL engine/version and network isolation; restore start/ready times; verifier JSON and exact application Git/image revision; local Alembic `heads` output and restored `alembic_version` agreement; critical workflow/canary results; achieved RPO/RTO calculations; object-store result or explicit “not implemented/no objects” attestation; incident decision; cleanup ticket and outcome. Hash evidence artifacts and store them in the approved restricted system, not this repository.

A pass requires fresh/healthy backup evidence, successful creation of a separate target, expected schema head without migration, validated constraints and core tables, representative PL read paths, a canary consistent with the restore point, objectives met, no production mutation, and no unhandled external side effects. Portal health alone, a Terraform value, or an Azure “Succeeded” status is insufficient.

## Meal-plan PDF/object-store gate

Before persisted PDFs ship, define a private tenant-scoped object store without changing the existing tenant model. Each database metadata row must bind organisation/tenant, immutable object key/version, content hash, size/type, creation and retention state; downloads must re-authorize ownership. Enable versioning or soft delete, encryption, retention/lifecycle, access logging, and—if regional recovery is claimed—tested cross-region recovery. Database and object recovery must use a common restore epoch or a reconciliation manifest.

Every drill must then inventory expected objects from restored metadata, verify object existence/version/size/hash using synthetic samples, reject orphan or cross-tenant access, regenerate only reproducible PDFs from immutable database inputs, and document handling for missing source assets. Database PITR does not restore blobs, and blob recovery does not restore authorization metadata.

## Incident decision: rollback or forward repair

Application rollback is appropriate when the previous image remains schema-compatible and the fault is in code/config: restore traffic through a reviewed Git change and retain the database. Do not run an Alembic downgrade during an incident. Use forward repair for additive migration defects, partial jobs, or data defects when compatibility remains; stop writers if continued writes worsen damage, preserve evidence, deploy a reviewed corrective migration/job, and validate invariants.

PITR to a new server is the last-resort data-loss path for corruption, destructive writes, or source loss. Choose and approve the restore point, quantify discarded writes, reconcile external systems, and cut over only after validation. Never overwrite the source. If an old application is incompatible with the current schema, rollback is unavailable: keep traffic off the incompatible version and repair forward. Regional loss currently requires an executive service decision because non-geo backups do not prove recoverability.

## Review cadence

Review backup freshness daily via monitoring, objectives and retention quarterly, and rehearse restore at least quarterly and after material database/storage topology changes. Exercise object recovery before enabling PDF persistence and quarterly thereafter. Track every failed check to closure; a missed or failed drill is an assurance failure, not a documentation exception.
