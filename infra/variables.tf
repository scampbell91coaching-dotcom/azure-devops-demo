variable "subscription_id" {
  description = "Azure Subscription ID"
  type        = string
}

variable "resource_group_name" {
  description = "Resource Group name"
  type        = string
}

variable "location" {
  description = "Azure region"
  type        = string
}

variable "acr_name" {
  description = "Globally unique Azure Container Registry name"
  type        = string

  validation {
    condition     = can(regex("^[a-zA-Z0-9]{5,50}$", var.acr_name))
    error_message = "ACR name must contain only letters and numbers and be between 5 and 50 characters."
  }
}

variable "postgresql_enabled" {
  description = "Enable the PostgreSQL foundation. Disabled by default so existing environments opt in explicitly."
  type        = bool
  default     = false
}

variable "key_vault_name" {
  description = "Name of the existing Key Vault used by External Secrets."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition     = !var.postgresql_enabled || (var.key_vault_name != null && can(regex("^[a-zA-Z0-9-]{3,24}$", var.key_vault_name)))
    error_message = "key_vault_name must be a valid Azure Key Vault name when PostgreSQL is enabled."
  }
}

variable "key_vault_resource_group_name" {
  description = "Resource group containing the existing Key Vault; defaults to the platform resource group."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition     = var.key_vault_resource_group_name == null || length(trimspace(var.key_vault_resource_group_name)) > 0
    error_message = "key_vault_resource_group_name must be null or a non-empty resource group name."
  }
}

variable "postgresql_server_name" {
  description = "Globally unique PostgreSQL Flexible Server name."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition     = !var.postgresql_enabled || (var.postgresql_server_name != null && can(regex("^[a-z0-9](?:[a-z0-9-]{1,61}[a-z0-9])$", var.postgresql_server_name)))
    error_message = "postgresql_server_name must be 3-63 lowercase letters, numbers, or hyphens and cannot start or end with a hyphen."
  }
}

variable "postgresql_administrator_login" {
  description = "PostgreSQL administrator login; the password is generated and stored in Key Vault."
  type        = string
  default     = "tsplatformadmin"

  validation {
    condition     = can(regex("^[a-zA-Z][a-zA-Z0-9_]{0,62}$", var.postgresql_administrator_login))
    error_message = "postgresql_administrator_login must start with a letter and contain at most 63 letters, numbers, or underscores."
  }
}

variable "postgresql_database_name" {
  description = "Dedicated application database name."
  type        = string
  default     = "traditional_strength"

  validation {
    condition     = can(regex("^[a-zA-Z][a-zA-Z0-9_]{0,62}$", var.postgresql_database_name))
    error_message = "postgresql_database_name must start with a letter and contain at most 63 letters, numbers, or underscores."
  }
}

variable "postgresql_sku_name" {
  description = "Flexible Server SKU; defaults to a cost-conscious burstable instance."
  type        = string
  default     = "B_Standard_B1ms"

  validation {
    condition     = can(regex("^(B|GP|MO)_Standard_[A-Za-z0-9_]+$", var.postgresql_sku_name))
    error_message = "postgresql_sku_name must be a valid Burstable, General Purpose, or Memory Optimized SKU name."
  }
}

variable "postgresql_storage_mb" {
  description = "Allocated PostgreSQL storage in MiB."
  type        = number
  default     = 32768

  validation {
    condition = contains([
      32768, 65536, 131072, 262144, 524288, 1048576, 2097152,
      4193280, 4194304, 8388608, 16777216, 33553408,
    ], var.postgresql_storage_mb)
    error_message = "postgresql_storage_mb must be a storage size supported by Azure PostgreSQL Flexible Server."
  }
}

variable "postgresql_backup_retention_days" {
  description = "Automated backup retention period in days."
  type        = number
  default     = 7

  validation {
    condition     = var.postgresql_backup_retention_days >= 7 && var.postgresql_backup_retention_days <= 35
    error_message = "postgresql_backup_retention_days must be between 7 and 35 days."
  }
}

variable "postgresql_geo_redundant_backup_enabled" {
  description = "Enable geo-redundant backups; disabled by default to control cost."
  type        = bool
  default     = false
}

variable "postgresql_high_availability_enabled" {
  description = "Enable zone-redundant or same-zone high availability."
  type        = bool
  default     = false
}

variable "postgresql_high_availability_mode" {
  description = "High availability mode used when PostgreSQL HA is enabled."
  type        = string
  default     = "ZoneRedundant"

  validation {
    condition     = contains(["SameZone", "ZoneRedundant"], var.postgresql_high_availability_mode)
    error_message = "postgresql_high_availability_mode must be SameZone or ZoneRedundant."
  }
}

variable "postgresql_private_dns_zone_name" {
  description = "Private DNS zone used by PostgreSQL Flexible Server."
  type        = string
  default     = "private.postgres.database.azure.com"

  validation {
    condition     = can(regex("(^|\\.)postgres\\.database\\.azure\\.com$", var.postgresql_private_dns_zone_name))
    error_message = "postgresql_private_dns_zone_name must end with postgres.database.azure.com."
  }
}

variable "postgresql_tags" {
  description = "Tags applied to PostgreSQL resources."
  type        = map(string)
  default = {
    Environment = "lab"
    ManagedBy   = "Terraform"
    Project     = "traditional-strength"
  }
}
