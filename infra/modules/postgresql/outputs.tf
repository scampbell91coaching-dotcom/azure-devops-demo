output "server_id" {
  description = "PostgreSQL Flexible Server resource ID."
  value       = azurerm_postgresql_flexible_server.this.id
}

output "fqdn" {
  description = "Private PostgreSQL server hostname for AKS workloads."
  value       = azurerm_postgresql_flexible_server.this.fqdn
}

output "database_name" {
  description = "Dedicated application database name."
  value       = azurerm_postgresql_flexible_server_database.application.name
}

output "port" {
  description = "PostgreSQL TLS port."
  value       = 5432
}

output "ssl_mode" {
  description = "SSL mode applications must use."
  value       = "verify-full"
}

output "private_dns_zone_id" {
  description = "Private DNS zone resource ID."
  value       = azurerm_private_dns_zone.this.id
}

output "key_vault_secret_names" {
  description = "Key Vault secret names consumed by External Secrets; values are intentionally not output."
  value = {
    host     = azurerm_key_vault_secret.host.name
    port     = azurerm_key_vault_secret.port.name
    database = azurerm_key_vault_secret.database.name
    username = azurerm_key_vault_secret.username.name
    password = azurerm_key_vault_secret.password.name
  }
}
