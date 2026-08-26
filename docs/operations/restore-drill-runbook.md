# Disposable PostgreSQL restore drill runbook

This runbook prepares and verifies a Traditional Strength point-in-time restore. It does not authorize an Azure restore, production change, credential change, cutover, or cleanup. Azure creation and deletion require the normal approval and an operator with the appropriate role. The repository tools are local/read-only and never invoke `az`.

## Safety contract

- Restore only to a newly created, isolated PostgreSQL server. Never restore over the source.
- Target resource ID, host, DNS, credentials, network and application configuration must differ from production.
- Give the target a delimiter-separated `restore`, `drill`, `disposable`, or `sandbox` token. Any `prod`, `production`, or `live` token makes tooling fail closed.
- Keep production DNS, GitOps, Key Vault, Kubernetes secrets and traffic unchanged.
- Disable email, billing, webhooks and background jobs in any isolated smoke-test application.
- Never put connection strings, names, emails, row data, PDF bytes, tokens or credentials in evidence.

## 1. Plan and read-only Azure preflight

Record the exercise/change ID, operator, approver, cleanup owner, exact application commit/image digest, expected Alembic head, source resource ID/FQDN, region, PostgreSQL version, retention/redundancy, earliest and latest restorable UTC points, provider health, and requested restore point. Use only approved read-only Azure inventory commands. Confirm the backup is healthy, retention is at least seven days, and the restore point is within the window.

Start an evidence directory in the approved restricted evidence store (not Git). Record the exercise start immediately before requesting restore. Generate the initial guard/timing record:

```bash
python scripts/backup_dr/restore_preflight.py \
  --rehearsal-id CHG-0000 \
  --source-resource-id '<full source Azure resource ID>' \
  --target-resource-id '<planned target Azure resource ID>' \
  --source-host '<source FQDN>' \
  --target-host '<target FQDN containing restore/drill/disposable/sandbox>' \
  --requested-restore-point 2026-08-18T10:00:00Z \
  --restore-started-at 2026-08-18T10:10:00Z \
  --output preflight.json
```

Exit 0 is required. Review the two distinct fingerprints and every check. RPO here is the requested restore point's age at exercise start; after recovery, the synthetic canary timestamp is the authoritative achieved-RPO proof.

## 2. Live Azure restore (approval required)

An authorized operator creates a **new** PITR server using the approved Azure procedure. Put it in the recovery resource group/subscription and isolated private network. Deny public and production-application access. Record operation ID and UTC start/ready timestamps. Do not run commands copied from evidence without separately resolving and reviewing their targets.

Create a temporary least-privilege verifier login through the approved secret channel. It needs database connect and SELECT/catalog access only. Do not run Alembic upgrade or any repair against the restore.

## 3. Schema and data verification

From the exact recovered/candidate release, independently determine that Alembic has one head:

```bash
cd platform-portal
python -m alembic -c migrations/alembic.ini heads
```

Set the secret URL only in the protected operator shell. Specify reviewed aggregate lower bounds from the last approved baseline; zero merely proves readable/present tables.

```bash
RESTORE_DATABASE_URL='<disposable restore URI>' \
python scripts/backup_dr/restore_verify.py \
  --source-host '<source FQDN>' \
  --expected-head 0026_programming_exposure_roles \
  --rehearsal-id CHG-0000 \
  --minimum-count athletes=1 \
  --minimum-count users=1 \
  --minimum-count training_sessions=1 \
  --minimum-count training_session_logs=1 \
  --minimum-count organisations=1 \
  --confirm I_CONFIRM_THIS_IS_A_DISPOSABLE_RESTORE \
  --output restore-verification.json
```

The verifier opens a read-only transaction with timeouts. It checks the exact single Alembic head; critical table presence and aggregate counts; validated constraints; valid/ready indexes; ownership consistency; visible sequence values against table maxima; and stored PDF lengths/hash metadata. The verifier credential therefore needs SELECT on owned sequences as well as tables. It independently recomputes every restored PDF SHA-256 in Python and compares the actual byte length with `content_length`; `pgcrypto` is not required. Evidence contains only aggregate PDF mismatch count/status, never PDF bytes, row content, filenames, athlete data, or hashes tied to identifiable records. A missing expected PDF table, any PDF mismatch, any other failed check, or a script error is a drill failure requiring stop-and-escalate investigation, not permission to mutate the restore.

## 4. Isolated smoke-test checklist

- [ ] Isolated deployment references only the target fingerprint; runtime and migration credentials are distinct.
- [ ] Outbound email, billing, webhooks, scheduled jobs and production integrations are disabled.
- [ ] Synthetic coach login works and lists only the expected organisation's athletes.
- [ ] A second-tenant synthetic identity cannot read the first tenant's athlete, programme, log, meal plan or PDF (expect 404/deny).
- [ ] Representative programme/session, training log and meal-plan assignment render correctly.
- [ ] A known PDF downloads only for its owning tenant; length and an operator-side SHA-256 match the approved synthetic baseline.
- [ ] A designated canary's last-known UTC timestamp brackets the requested point and gives achieved data-loss/RPO.
- [ ] Optional write/reload uses synthetic data only and is done solely in the isolated restore with explicit exercise approval.
- [ ] No request reached production and no external side effect was emitted.

## 5. Final timing and evidence

Rerun `restore_preflight.py` with `--restore-ready-at` and `--validation-finished-at` to capture restore duration and total measured RTO. Traditional Strength's current operational objectives are RPO 15 minutes and RTO 240 minutes for a recoverable database/server event. Record exceptions and owner; a passing requested-point calculation does not override a failing canary measurement.

Retain: approval, sanitized Azure inventory/operation output, source/target fingerprints, commit and image digest, local Alembic heads output, both JSON files, count baselines, smoke results, requested and achieved RPO, measured RTO, failures, reviewer decision, and cleanup ticket. Hash each evidence file (for example `sha256sum`) after redaction and store the manifest with the restricted bundle.

## 6. Cleanup checklist (separate approval)

- [ ] Reviewer accepts the evidence and confirms no retest/retention hold requires the restore.
- [ ] Resolve source and target resource IDs again; compare them with the accepted fingerprints.
- [ ] Confirm production DNS, GitOps, workloads, Key Vault and connections still reference the source.
- [ ] Obtain explicit Azure deletion approval naming only the disposable target resource ID.
- [ ] Revoke the temporary verifier/runtime credentials and remove temporary recovery-network access.
- [ ] Authorized operator deletes only the disposable target and records operation ID/time. These repository scripts do not delete it.
- [ ] Confirm the target is absent and production health is unchanged.
- [ ] Attach sanitized cleanup proof and reviewer sign-off; record evidence expiry and remediation owners.

Stop and escalate on ambiguous identity, a production-like target, missing approval, unhealthy/stale backup, a verifier failure, unexpected tenant ownership, missing PDF proof, unmet RPO/RTO, or any indication that production configuration changed.
