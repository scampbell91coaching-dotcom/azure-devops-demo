module "resource_group" {
  source = "./modules/resource-group"

  name     = var.resource_group_name
  location = var.location
  tags     = {}
}

module "network" {
  source = "./modules/network"

  resource_group_name          = module.resource_group.name
  location                     = module.resource_group.location
  enable_postgresql_delegation = var.postgresql_enabled
}

module "monitoring" {
  source = "./modules/monitoring"

  resource_group_name = module.resource_group.name
  location            = module.resource_group.location
}

data "azurerm_key_vault" "application" {
  count = var.postgresql_enabled ? 1 : 0

  name                = var.key_vault_name
  resource_group_name = coalesce(var.key_vault_resource_group_name, module.resource_group.name)
}

module "postgresql" {
  count  = var.postgresql_enabled ? 1 : 0
  source = "./modules/postgresql"

  name                             = var.postgresql_server_name
  resource_group_name              = module.resource_group.name
  location                         = module.resource_group.location
  delegated_subnet_id              = module.network.database_subnet_id
  virtual_network_id               = module.network.virtual_network_id
  additional_virtual_network_links = var.postgresql_additional_virtual_network_links
  key_vault_id                     = data.azurerm_key_vault.application[0].id
  administrator_login              = var.postgresql_administrator_login
  database_name                    = var.postgresql_database_name
  sku_name                         = var.postgresql_sku_name
  storage_mb                       = var.postgresql_storage_mb
  backup_retention_days            = var.postgresql_backup_retention_days
  geo_redundant_backup_enabled     = var.postgresql_geo_redundant_backup_enabled
  high_availability_enabled        = var.postgresql_high_availability_enabled
  high_availability_mode           = var.postgresql_high_availability_mode
  private_dns_zone_name            = var.postgresql_private_dns_zone_name
  tags                             = var.postgresql_tags
}
