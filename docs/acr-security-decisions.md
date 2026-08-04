# Azure Container Registry security decisions

Status: accepted for the current single-region lab architecture, reviewed 2026-08-04.

## Current boundary and consumers

`infra/acr.tf` creates one Basic Azure Container Registry (ACR). The registry admin account is explicitly disabled, so consumers authenticate with Microsoft Entra identities or service connections rather than the registry-wide administrator credential.

The repository shows three network consumers:

- GitHub-hosted Actions build, scan, and push images in `.github/workflows/app-deploy.yml` and `.github/workflows/lead-magnets-deploy.yml`.
- Microsoft-hosted Azure Pipelines agents push images in `azure-pipelines.yml`.
- AKS looks up this registry and receives `AcrPull` in `infra/aks/main.tf`.

The affected Terraform root has no ACR private endpoint, `privatelink.azurecr.io` private DNS zone, or private CI runner. Public network access therefore remains explicitly enabled. Disabling it in isolation would break hosted build/push traffic and could break image pulls. A future private-access change must provide a dedicated private-endpoint subnet, private DNS linkage and records for every ACR endpoint, AKS DNS/routing validation, and network-connected CI runners before public access is disabled. AKS and subnet resources are outside this change.

## Control disposition

| Check | Disposition | Evidence and reason |
| --- | --- | --- |
| Admin account | Implemented | `admin_enabled = false` prevents use of the shared registry administrator credential. |
| CKV_AZURE_163 vulnerability scanning | Exception: unavailable on this resource | AzureRM exposes no ACR resource flag that enables Azure-native vulnerability assessment. Microsoft documents scanning as a Microsoft Defender for Cloud plan/extension capability. Checkov only tests whether the SKU is Standard or Premium, which is not proof that Defender is enabled. Repository and final-image Trivy scans provide CI evidence, but they are point-in-time pipeline gates and do not replace Defender's registry inventory, continuous re-scan, or Azure recommendations. Defender plan enablement is subscription-scoped and outside this root. |
| CKV_AZURE_164 signed/trusted images | Exception: deprecated control | The check requires ACR Docker Content Trust. Microsoft deprecated DCT from 2025-03-31, blocks enabling it on new or previously unenabled registries from 2026-05-31, and will remove it on 2028-03-31. It must not be newly enabled. The supported successor needs Notary Project/Notation signing plus verification in CI and at AKS admission; neither half is present, so this is an explicit supply-chain gap rather than a compliance claim. |
| CKV_AZURE_165 geo-replication | Deferred architecture/cost decision | Geo-replication requires Premium and at least one chosen secondary Azure region. The repository describes a single-region deployment and provides no recovery region, latency target, or regional private networking. A Premium upgrade and replica charges require an availability and cost decision. |
| CKV_AZURE_166 quarantine and verified images | Exception: unavailable on chosen SKU and incomplete alone | ACR quarantine is a Premium policy intended for an external processing workflow to inspect and mark images. This Basic registry cannot safely enable it, and setting the policy without a processor would not provide scanning or verification. Existing Trivy gates run before push, but do not constitute the Azure quarantine lifecycle asserted by this check. |
| CKV_AZURE_167 untagged-manifest retention | Deferred cost decision | Microsoft documents retention as a Premium-only preview. AzureRM 4.81.0 supports `retention_policy_in_days`, but the chosen Basic SKU does not. The registry is deliberately not upgraded solely to pass the check. If Premium is approved, add a reviewed non-zero retention period after confirming rollback images and OCI-manifest behavior. |
| CKV_AZURE_139 public networking | Deferred architecture decision | Public access is required by the current hosted CI consumers. Private Link also requires Premium. Disable public access only with the coherent private endpoint, DNS, AKS and private-runner design described above. |
| CKV_AZURE_233 zone redundancy | Exception: obsolete configuration test | Microsoft now enables ACR data-plane zone redundancy automatically for every SKU in availability-zone-supported regions. The `zoneRedundancy` ARM property is a legacy artifact that no longer controls behavior and is planned for deprecation. Actual coverage depends on selecting a supported `var.location`; setting the legacy flag would not make an unsupported region redundant. |
| CKV_AZURE_237 dedicated data endpoints | Deferred architecture/cost decision | Registry-specific layer endpoints reduce wildcard storage egress rules but require Premium. They are automatically enabled with ACR Private Link and should be adopted with the private networking design, firewall rules and DNS records rather than as an isolated paid SKU change. |

## Evidence sources

- Microsoft, [Vulnerability assessments for supported environments](https://learn.microsoft.com/azure/defender-for-cloud/agentless-vulnerability-assessment-azure)
- Microsoft, [Transition from Docker Content Trust to Notary Project](https://learn.microsoft.com/azure/container-registry/container-registry-content-trust-deprecation)
- Microsoft, [Set a retention policy for untagged manifests](https://learn.microsoft.com/azure/container-registry/container-registry-retention-policy)
- Microsoft, [Connect privately to an ACR using Azure Private Link](https://learn.microsoft.com/azure/container-registry/container-registry-private-endpoints)
- Microsoft, [Geo-replication in Azure Container Registry](https://learn.microsoft.com/azure/container-registry/container-registry-geo-replication)
- Microsoft, [Zone redundancy in Azure Container Registry](https://learn.microsoft.com/azure/container-registry/zone-redundancy)
- Microsoft, [Dedicated data endpoints in Azure Container Registry](https://learn.microsoft.com/azure/container-registry/container-registry-dedicated-data-endpoints)
- HashiCorp AzureRM 4.81.0, [container registry resource](https://registry.terraform.io/providers/hashicorp/azurerm/4.81.0/docs/resources/container_registry)

These sources describe service capability, not the live subscription state. No claim is made here that Defender, availability-zone regional support, signing, admission verification, or private connectivity is enabled outside this repository.
