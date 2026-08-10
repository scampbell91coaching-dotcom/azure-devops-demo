# Agent E report — V7.6 Blue/Green implementation readiness

Produced the requested repository-grounded implementation plan in `docs/v7.6-blue-green-implementation-readiness.md`. No production manifests, workflows, migrations, Azure resources, Argo CD resources, or live systems were changed, and nothing was merged.

## Conclusions

- The RWO `platform-portal-private-data` PVC is an orphaned/non-authoritative runtime mount. Production state is PostgreSQL, immutable catalogue data is under `/app/data`, and status data uses the separate RWX `/status` claim. The plan removes `/data` from both slots, retains the claim through the rollback window, and deletes it only after a read-only live preflight and separate approval.
- Selector-only traffic changes must be isolated in a separate `private-platform-manifests/traffic` Argo Application/path. Release resources and the PreSync migration/seed Job remain under `private-platform-manifests/release`; this prevents a traffic Application sync from executing the release hook.
- The target has two fixed Deployments and direct Services, while the stable `platform-portal-private` Service selects exactly one slot. Public Ingress, hostname, TLS and OAuth callback remain unchanged.
- Promotion updates only the inactive slot and deterministic release Job. Cutover is a separate, approved, one-field Git commit. The old slot is retained unchanged for rollback.
- Status collection becomes schema-v2 and reports stable selector identity plus independent Blue/Green image, readiness, restart and health state. CI and operator tooling stop using the single-Deployment assumption.
- Three overlapping portal NetworkPolicies are replaced by one common-label portal rule covering both slots, plus the distinct OAuth and ACME rules.
- Database rollback is traffic rollback plus forward-fix. Expand/migrate/contract compatibility is a hard cutover gate; contract work waits until the old slot is deliberately retired.

## Deliverables and validation

The plan contains exact file additions/moves/edits, reconciliation ownership, promotion and rollback contracts, implementation phases with go/failure checkpoints, and the full offline/disposable-environment test gate. Canary is preserved only as a future routing extension point.

Validation performed for this documentation task was static repository inspection and cross-reference tracing. No live query or mutation was performed. The implementation plan explicitly requires a later authorized read-only `/data` inspection because repository evidence cannot prove the contents of the live volume.
