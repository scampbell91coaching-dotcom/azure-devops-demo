subscription_id     = "abac1d73-0524-4172-a292-64f8a7595728"
resource_group_name = "rg-devops-assessment-lab"
location            = "eastus2"
acr_name            = "stevedevopslab6280"

# PostgreSQL is live in this environment. Keep these values in the canonical
# CI var file so a normal root plan can never disable the managed foundation.
postgresql_enabled                      = true
postgresql_server_name                  = "psql-traditional-strength-6280"
postgresql_database_name                = "traditional_strength"
postgresql_administrator_login          = "tsplatformadmin"
key_vault_name                          = "stevedevopskv30841"
key_vault_resource_group_name           = "rg-devops-assessment-lab"
postgresql_sku_name                     = "B_Standard_B1ms"
postgresql_storage_mb                   = 32768
postgresql_backup_retention_days        = 7
postgresql_geo_redundant_backup_enabled = false
postgresql_high_availability_enabled    = false

postgresql_additional_virtual_network_links = {
  aks-devops-lab = "/subscriptions/abac1d73-0524-4172-a292-64f8a7595728/resourceGroups/MC_rg-devops-assessment-lab_aks-devops-lab_eastus2/providers/Microsoft.Network/virtualNetworks/aks-vnet-38128856"
}

terraform_key_vault_reader_principal_id = "cf1d314b-b660-4c3d-997c-df4e2589c646"
