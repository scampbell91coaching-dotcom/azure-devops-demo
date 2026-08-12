# Platform documentation

Start with the evidence-scoped documents below. They describe repository state
without treating screenshots or historical status as proof of a current live
deployment.

## Core review path

| Document | Purpose |
| --- | --- |
| [Platform engineering case study](platform-engineering-case-study.md) | Recruiter and client-facing account of the architecture, delivery model, incidents, security evolution and evidenced trade-offs |
| [Architecture](architecture.md) | System boundaries, AKS, Terraform, networking, GitOps, data, identity and implemented/planned classification |
| [Security architecture](security.md) | Trust boundaries, secret and identity flows, Kubernetes controls, supply chain and evidenced gaps |
| [Operations and recovery](operations.md) | Release gates, rollback, managed backups, PITR procedure and recovery posture |
| [Engineering decisions](engineering-decisions.md) | ADR-style decisions supported by current executable configuration |
| [Limitations](limitations.md) | Current constraints and explicit V6/SaaS non-capabilities |
| [Roadmap](roadmap.md) | Future reliability and product boundaries; not current capability |

## Deep dives and runbooks

| Document | Purpose |
| --- | --- |
| [Networking](networking.md) | Azure and Kubernetes network paths, DNS dependencies and public exposure |
| [Azure PostgreSQL](azure-postgresql.md) | Provisioning details, database cutover and PITR procedure |
| [Backup/DR restore assurance](backup-dr-restore-assurance.md) | RPO/RTO, non-destructive restore rehearsal, evidence gates and file-store recovery boundary |
| [Observability current state](observability-current-state.md) | Repository audit separating foundations from active telemetry |
| [Operational runbook](runbook.md) | Diagnostic and containment commands for authorized operators |
| [Release documentation](release/README.md) | Release evidence, checklist and rollback template |
| [Identity and runtime audit](security/identity-and-runtime-audit.md) | Detailed identity and runtime control audit |
| [AKS deferred controls](security/aks-deferred-controls.md) | Accepted AKS gaps and exit criteria |
| [Powerlifting multi-coach beta readiness](beta-readiness/README.md) | Conditional onboarding, acceptance, smoke, support, incident and restore package; currently NO-GO for a shared multi-coach beta |

## Supporting and historical material

| Document | Purpose |
| --- | --- |
| [Engineering overview](engineering-overview.md) | Read-only portal index and status model |
| [Interview talking points](interview-talking-points.md) | Repository-specific discussion prompts |
| [Version 1 summary](version-1-summary.md) | Historical delivery summary; validate claims against current code |
| [Production observability](production-observability.md) | Proposed monitoring design, not active production capability |
| [Production backlog](production-backlog.md) | Deferred hardening work and exit criteria |
| [Azure metadata inventory](azure-inventory.md) | Read-only inventory procedure; not a current-state snapshot |
| [Credential coverage audit](../scripts/credentials/README.md) | Metadata-only credential coverage reporting |
