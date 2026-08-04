variable "name" {
  description = "Globally unique PostgreSQL Flexible Server name."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9](?:[a-z0-9-]{1,61}[a-z0-9])$", var.name))
    error_message = "name must be 3-63 lowercase letters, numbers, or hyphens and cannot start or end with a hyphen."
  }
}

variable "resource_group_name" {
  description = "Resource group in which PostgreSQL resources are created."
  type        = string
}

variable "location" {
  description = "Azure region for PostgreSQL resources."
  type        = string
}

variable "delegated_subnet_id" {
  description = "ID of a subnet delegated to Microsoft.DBforPostgreSQL/flexibleServers."
  type        = string
}

variable "virtual_network_id" {
  description = "ID of the virtual network linked to the PostgreSQL private DNS zone."
  type        = string
}

variable "key_vault_id" {
  description = "ID of the existing Key Vault in which connection values are stored."
  type        = string
}

variable "administrator_login" {
  description = "PostgreSQL administrator login."
  type        = string
  default     = "tsplatformadmin"

  validation {
    condition = (
      can(regex("^[a-zA-Z][a-zA-Z0-9_]{0,62}$", var.administrator_login)) &&
      !contains(["admin", "administrator", "azure_pg_admin", "azure_superuser", "guest", "public", "root"], lower(var.administrator_login))
    )
    error_message = "administrator_login must start with a letter, contain at most 63 letters, numbers, or underscores, and not use a reserved administrator name."
  }
}

variable "database_name" {
  description = "Dedicated application database name."
  type        = string
  default     = "traditional_strength"

  validation {
    condition     = can(regex("^[a-zA-Z][a-zA-Z0-9_]{0,62}$", var.database_name))
    error_message = "database_name must start with a letter and contain at most 63 letters, numbers, or underscores."
  }
}

variable "postgresql_version" {
  description = "PostgreSQL major version."
  type        = string
  default     = "16"

  validation {
    condition     = contains(["14", "15", "16", "17", "18"], var.postgresql_version)
    error_message = "postgresql_version must be one of 14, 15, 16, 17, or 18."
  }
}

variable "sku_name" {
  description = "Flexible Server compute SKU."
  type        = string
  default     = "B_Standard_B1ms"

  validation {
    condition     = can(regex("^(B|GP|MO)_Standard_[A-Za-z0-9_]+$", var.sku_name))
    error_message = "sku_name must be a valid Burstable, General Purpose, or Memory Optimized SKU name."
  }
}

variable "storage_mb" {
  description = "Allocated storage in MiB."
  type        = number
  default     = 32768

  validation {
    condition = contains([
      32768, 65536, 131072, 262144, 524288, 1048576, 2097152,
      4193280, 4194304, 8388608, 16777216, 33553408,
    ], var.storage_mb)
    error_message = "storage_mb must be a storage size supported by Azure PostgreSQL Flexible Server."
  }
}

variable "backup_retention_days" {
  description = "Automated backup retention in days."
  type        = number
  default     = 7

  validation {
    condition     = var.backup_retention_days >= 7 && var.backup_retention_days <= 35
    error_message = "backup_retention_days must be between 7 and 35 days."
  }
}

variable "geo_redundant_backup_enabled" {
  description = "Whether backups are geo-redundant."
  type        = bool
  default     = false
}

variable "high_availability_enabled" {
  description = "Whether to enable Flexible Server high availability."
  type        = bool
  default     = false
}

variable "high_availability_mode" {
  description = "High availability mode."
  type        = string
  default     = "ZoneRedundant"

  validation {
    condition     = contains(["SameZone", "ZoneRedundant"], var.high_availability_mode)
    error_message = "high_availability_mode must be SameZone or ZoneRedundant."
  }
}

variable "private_dns_zone_name" {
  description = "Private DNS zone name for Flexible Server."
  type        = string
  default     = "private.postgres.database.azure.com"

  validation {
    condition     = can(regex("(^|\\.)postgres\\.database\\.azure\\.com$", var.private_dns_zone_name))
    error_message = "private_dns_zone_name must end with postgres.database.azure.com."
  }
}

variable "tags" {
  description = "Tags applied to resources."
  type        = map(string)
  default     = {}

  validation {
    condition     = alltrue([for key, value in var.tags : length(trimspace(key)) > 0 && length(trimspace(value)) > 0])
    error_message = "tags cannot contain empty or whitespace-only keys or values."
  }
}
