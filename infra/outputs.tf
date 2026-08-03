output "application_insights_connection_string" {
  description = "Application Insights connection string"
  value       = module.monitoring.application_insights_connection_string
  sensitive   = true
}

output "postgresql_connection" {
  description = "Non-secret PostgreSQL connection metadata for AKS configuration."
  value = var.postgresql_enabled ? {
    host        = module.postgresql[0].fqdn
    port        = module.postgresql[0].port
    database    = module.postgresql[0].database_name
    ssl_mode    = module.postgresql[0].ssl_mode
    secret_refs = module.postgresql[0].key_vault_secret_names
  } : null
}
