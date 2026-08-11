# Blue/green current implementation audit report

## Outcome

Completed a read-only design audit at base `7d77bdc` and produced [the detailed V7.9 review](docs/v7.9-bluegreen-current-implementation-review.md). No live cluster, Argo CD, Azure, registry, DNS, OAuth, database or production action was taken. No merge or deploy was performed, and no implementation manifest was changed.

Decision: **NO-GO for blue/green cutover from the current manifests.** The repository still implements a single migration-gated rolling Deployment. The earlier V7.6 fixed-slot design is documented but not implemented.

## Principal findings

- `Service/platform-portal-private` selects a broad application label; Blue/Green workloads, slot labels, direct slot Services, inactive-slot promotion and selector-only cutover do not exist.
- Traffic and release resources share one automated Argo Application/path, so a future selector cutover is not isolated from the PreSync migration/seed Job.
- The portal mounts the same RWO PVC at `/data`. Repository evidence suggests it is non-authoritative, but only a separately authorized sanitized live inspection can prove it safe to unmount. Dual-slot placement must not rely on RWO co-scheduling.
- Stable ingress/OAuth identities are suitable to retain: hostname, TLS secret, stable backends, auth URL/sign-in headers, cookie and callback should remain unchanged. Current verification proves only an anonymous 302, not callback/session/authenticated application success.
- Three overlapping portal NetworkPolicy definitions include a duplicate resource identity. They need one slot-neutral portal policy, a distinct OAuth policy and the existing ACME rule, with disposable-cluster allow/deny tests.
- Portal, migration and collector application images currently share the same full-SHA tag, but promotion changes all single-release references and cannot preserve an active slot. Candidate promotion must be inactive-only and digest-verifiable.
- Expand/migrate/contract compatibility is documentation, not an enforced gate. Cutover must require the retained image and candidate image both to operate after migration; contract changes wait until rollback retirement.
- Collector, CI and operator verification name one Deployment and sometimes select the first broad-label pod. They must report and verify the stable selector, both named slots, direct/stable health, exact images and EndpointSlice membership.
- Rollback must be a reviewed selector-only Git commit with database forward-fix. Direct patches will conflict with Argo self-heal, and migration downgrade/restore is a separate data-affecting decision.

## Required gate

Before any separately authorized production proposal: split Argo release/traffic ownership; resolve `/data`; introduce two fixed slots and direct Services; consolidate policies; add YAML-aware promotion/switch tooling; rehearse PostgreSQL compatibility and double switching; and prove unchanged ingress/OAuth plus authenticated behavior. Any ambiguous selector, image mismatch, unexplained PVC writer, incompatible old image, failed backup gate, duplicate ownership or failed direct-slot health is a stop condition.

## Validation scope

Validation for this task is repository-static only. The audit covers stable Service switching, ingress/OAuth stability, migration isolation, RWO storage, NetworkPolicies, image consistency, expand/contract database policy, preflight, rollback and verification. Live state and behavior remain explicitly unverified.
