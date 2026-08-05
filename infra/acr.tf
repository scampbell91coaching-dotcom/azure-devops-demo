resource "azurerm_container_registry" "main" {
  # checkov:skip=CKV_AZURE_163:ACR has no per-registry scanning flag; Defender plan enablement is subscription-scoped and is not managed in this root.
  # checkov:skip=CKV_AZURE_164:Azure deprecated Docker Content Trust and blocks new enablement; Notary signing and admission verification require a separate design.
  # checkov:skip=CKV_AZURE_165:Geo-replication requires Premium and a second-region architecture; this single-region lab intentionally retains Basic.
  # checkov:skip=CKV_AZURE_166:Quarantine requires Premium plus an external processing workflow; enabling the policy alone would not scan or verify images.
  # checkov:skip=CKV_AZURE_167:Untagged-manifest retention is a Premium-only preview; the Basic registry cannot express it safely.
  # checkov:skip=CKV_AZURE_139:Public access remains required by hosted CI; no private endpoint, DNS zone, or private CI runners exist in this root.
  # checkov:skip=CKV_AZURE_233:Azure now provides zone redundancy automatically in supported regions; the checked ARM property is legacy and does not control it.
  # checkov:skip=CKV_AZURE_237:Dedicated data endpoints require Premium; adopting them is coupled to the deferred private-network architecture.
  name                          = var.acr_name
  resource_group_name           = module.resource_group.name
  location                      = module.resource_group.location
  sku                           = "Basic"
  admin_enabled                 = false
  public_network_access_enabled = true

  tags = {
    Environment = "production"
    ManagedBy   = "Terraform"
  }
}

output "acr_name" {
  description = "Azure Container Registry name"
  value       = azurerm_container_registry.main.name
}

output "acr_login_server" {
  description = "Azure Container Registry login server"
  value       = azurerm_container_registry.main.login_server
}

output "acr_id" {
  description = "Azure Container Registry resource ID"
  value       = azurerm_container_registry.main.id
}
