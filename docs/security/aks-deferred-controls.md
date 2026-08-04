# AKS Deferred Security Controls

## CKV_AZURE_115: Private AKS cluster

Status: Deferred

Reason:

- Private-cluster mode changes API-server connectivity and DNS.
- GitHub-hosted CI, operator access, Argo CD and emergency access require a tested private-network path.
- This will be implemented as a dedicated production networking change rather than as a static-analysis-only modification.

Exit criteria:

- Private DNS design approved.
- CI runner connectivity available.
- Operator and emergency access tested.
- Rollback procedure documented.
- Terraform plan reviewed inside a maintenance window.

## CKV_AZURE_117: Disk Encryption Set

Status: Deferred

Reason:

- Customer-managed disk encryption requires Key Vault or Managed HSM resources.
- Managed identities and key permissions must be designed.
- Key rotation, recovery and deletion protection introduce operational responsibilities.
- Azure-managed encryption and AKS host encryption remain enabled in the current design.

Exit criteria:

- Key ownership and rotation policy approved.
- Key Vault recovery controls configured.
- Identity permissions tested.
- Cost and operational overhead accepted.
- Restore and rollback procedures validated.
