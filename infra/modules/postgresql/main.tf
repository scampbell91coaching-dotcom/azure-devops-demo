resource "random_password" "administrator" {
  length           = 32
  special          = true
  min_lower        = 1
  min_numeric      = 1
  min_special      = 1
  min_upper        = 1
  override_special = "!#$%&*+-=?@^_"
}

resource "azurerm_private_dns_zone" "this" {
  name                = var.private_dns_zone_name
  resource_group_name = var.resource_group_name
  tags                = var.tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "this" {
  name                  = "${var.name}-vnet-link"
  private_dns_zone_name = azurerm_private_dns_zone.this.name
  virtual_network_id    = var.virtual_network_id
  resource_group_name   = var.resource_group_name
  registration_enabled  = false
  tags                  = var.tags
}

resource "azurerm_postgresql_flexible_server" "this" {
  #checkov:skip=CKV_AZURE_136:Geo-redundant backup is an explicit, region-dependent cost option; local PITR remains enabled.
  #checkov:skip=CKV2_AZURE_57:Flexible Server private access uses a delegated subnet and private DNS, not a Private Endpoint.
  name                          = var.name
  resource_group_name           = var.resource_group_name
  location                      = var.location
  version                       = var.postgresql_version
  delegated_subnet_id           = var.delegated_subnet_id
  private_dns_zone_id           = azurerm_private_dns_zone.this.id
  public_network_access_enabled = false

  administrator_login    = var.administrator_login
  administrator_password = random_password.administrator.result

  sku_name                     = var.sku_name
  storage_mb                   = var.storage_mb
  auto_grow_enabled            = true
  backup_retention_days        = var.backup_retention_days
  geo_redundant_backup_enabled = var.geo_redundant_backup_enabled

  dynamic "high_availability" {
    for_each = var.high_availability_enabled ? [1] : []

    content {
      mode = var.high_availability_mode
    }
  }

  maintenance_window {
    day_of_week  = 0
    start_hour   = 3
    start_minute = 0
  }

  tags = var.tags

  depends_on = [azurerm_private_dns_zone_virtual_network_link.this]

  lifecycle {
    # Deletion requires an explicit, reviewed code change as well as a destroy plan.
    prevent_destroy = true

    precondition {
      condition     = !var.high_availability_enabled || !startswith(var.sku_name, "B_")
      error_message = "High availability is not supported with Burstable SKUs; select an eligible General Purpose or Memory Optimized SKU."
    }
  }
}

resource "azurerm_postgresql_flexible_server_configuration" "require_secure_transport" {
  name      = "require_secure_transport"
  server_id = azurerm_postgresql_flexible_server.this.id
  value     = "on"
}

resource "azurerm_postgresql_flexible_server_configuration" "minimum_tls_version" {
  name      = "ssl_min_protocol_version"
  server_id = azurerm_postgresql_flexible_server.this.id
  value     = "TLSv1.2"
}

resource "azurerm_postgresql_flexible_server_database" "application" {
  name      = var.database_name
  server_id = azurerm_postgresql_flexible_server.this.id
  collation = "en_US.utf8"
  charset   = "UTF8"
}

resource "azurerm_key_vault_secret" "host" {
  #checkov:skip=CKV_AZURE_41:Service metadata follows the server lifecycle; arbitrary expiry would break consumers without a rotation controller.
  name         = "${var.name}-host"
  value        = azurerm_postgresql_flexible_server.this.fqdn
  key_vault_id = var.key_vault_id
  content_type = "text/plain"
  tags         = var.tags
}

resource "azurerm_key_vault_secret" "port" {
  #checkov:skip=CKV_AZURE_41:Service metadata follows the server lifecycle; arbitrary expiry would break consumers without a rotation controller.
  name         = "${var.name}-port"
  value        = "5432"
  key_vault_id = var.key_vault_id
  content_type = "text/plain"
  tags         = var.tags
}

resource "azurerm_key_vault_secret" "database" {
  #checkov:skip=CKV_AZURE_41:Service metadata follows the server lifecycle; arbitrary expiry would break consumers without a rotation controller.
  name         = "${var.name}-database"
  value        = azurerm_postgresql_flexible_server_database.application.name
  key_vault_id = var.key_vault_id
  content_type = "text/plain"
  tags         = var.tags
}

resource "azurerm_key_vault_secret" "username" {
  #checkov:skip=CKV_AZURE_41:The username follows the server lifecycle; arbitrary expiry would break consumers without a rotation controller.
  name         = "${var.name}-username"
  value        = var.administrator_login
  key_vault_id = var.key_vault_id
  content_type = "text/plain"
  tags         = var.tags
}

resource "azurerm_key_vault_secret" "password" {
  #checkov:skip=CKV_AZURE_41:Expiry without automated credential rotation would cause an outage; rotation is an explicit operational procedure.
  name         = "${var.name}-password"
  value        = random_password.administrator.result
  key_vault_id = var.key_vault_id
  content_type = "text/plain"
  tags         = var.tags
}
