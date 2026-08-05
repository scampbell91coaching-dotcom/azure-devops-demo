# Production backlog


## Enable AKS production node-pool host encryption

**Priority:** Security hardening  
**Status:** Blocked by Azure quota

Enable `host_encryption_enabled` on the `production` AKS user node pool.

Azure requires a temporary rotation node for this change. The apply attempted on
2026-08-05 failed because the subscription had no remaining regional vCPU quota
in East US 2 and the temporary two-vCPU node could not be created.

### Completion criteria

- Increase the applicable East US 2 regional or VM-family vCPU quota.
- Re-enable `host_encryption_enabled = true`.
- Configure `temporary_name_for_rotation` for the production node pool.
- Confirm a Terraform plan with zero destroys and zero replacements.
- Apply successfully.
- Remove the `CKV_AZURE_227` Checkov exception.
- Verify Checkov passes without the exception.

