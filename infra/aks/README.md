# AKS Terraform baseline

This Terraform root manages the AKS cluster separately from the platform root in
`infra/`. The platform root creates the Log Analytics workspace; pass its name as
`log_analytics_workspace_name` so the AKS root can look it up without duplicating
the workspace or hard-coding an Azure resource ID. Apply the platform root before
planning this root in a new environment.

## Baseline security decisions

The system node pool uses the AKS Standard pricing tier, limits each node to 50
pods, and carries the `CriticalAddonsOnly=true:NoSchedule` taint. Azure Monitor for
containers sends cluster telemetry to the existing Log Analytics workspace.

The dev environment uses `Standard_D2s_v3` nodes and a 30 GiB ephemeral OS disk.
Microsoft documents ephemeral OS disk support and a 50 GiB disk cache for this
SKU, so the configured OS disk fits in the available cache. Changing
`max_pods`, the critical-addons taint, or the OS disk type cycles the system node
pool. `temporary_name_for_rotation` allows AzureRM to perform that rotation, but
the provider warns that cycling the system pool does not cordon and drain it.
Schedule the first deployment in a maintenance window and confirm workloads have
replicas and disruption budgets.

Host encryption (CKV_AZURE_227) remains deferred. AzureRM can express
`host_encryption_enabled`, but Azure requires the
`Microsoft.Compute/EncryptionAtHost` subscription feature to be registered and
the selected SKU to report `EncryptionAtHostSupported` in the deployment region.
This repository cannot establish those subscription capabilities safely. Verify
both prerequisites before enabling it; enabling it also rotates the system node
pool.

## Deferred architecture findings

The following findings are intentionally documented, not globally skipped:

- CKV_AZURE_115: private-cluster conversion requires DNS, network connectivity,
  operator access, and CI runner design. It is outside this baseline branch.
- CKV_AZURE_117: a disk encryption set requires key lifecycle, permissions,
  recovery, and rotation architecture. It is outside this baseline branch.
- CKV_AZURE_6: the existing authorized-IP input is preserved, but selecting and
  maintaining trusted operator and CI egress CIDRs is environment-specific. No
  ranges are invented here.

Do not suppress these checks globally. Resolve them through an approved
architecture decision and environment-specific rollout.
