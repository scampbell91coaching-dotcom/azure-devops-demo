variable "subscription_id" {
  description = "Azure subscription ID"
  type        = string
}

variable "resource_group_name" {
  description = "Existing Azure resource group"
  type        = string
  default     = "rg-devops-assessment-lab"
}

variable "location" {
  description = "Azure region"
  type        = string
  default     = "eastus2"
}

variable "aks_name" {
  description = "AKS cluster name"
  type        = string
  default     = "aks-devops-lab"
}

variable "dns_prefix" {
  description = "AKS DNS prefix"
  type        = string
  default     = "aks-devops-lab"
}

variable "api_server_authorized_ip_ranges" {
  description = "Public CIDR ranges allowed to reach the AKS API; supply trusted operator and CI egress ranges"
  type        = list(string)

  validation {
    condition = length(var.api_server_authorized_ip_ranges) > 0 && alltrue([
      for address in var.api_server_authorized_ip_ranges :
      can(cidrhost(strcontains(trimspace(address), "/") ? trimspace(address) : "${trimspace(address)}/32", 0))
    ])
    error_message = "At least one valid trusted AKS API server IP address or CIDR must be supplied."
  }
}

variable "acr_name" {
  description = "Existing Azure Container Registry name"
  type        = string
  default     = "stevedevopslab6280"
}

variable "log_analytics_workspace_name" {
  description = "Name of the existing Log Analytics workspace used by Azure Monitor for containers"
  type        = string
  default     = "law-devops-lab"

  validation {
    condition     = length(trimspace(var.log_analytics_workspace_name)) > 0
    error_message = "log_analytics_workspace_name must not be empty."
  }
}

variable "node_vm_size" {
  description = "VM size used by the AKS system node pool"
  type        = string
  default     = "Standard_B2s"
}

variable "node_count" {
  description = "Initial number of AKS nodes"
  type        = number
  default     = 2
}

variable "min_node_count" {
  description = "Minimum number of nodes used by the cluster autoscaler"
  type        = number
  default     = 2
}

variable "max_node_count" {
  description = "Maximum number of nodes used by the cluster autoscaler"
  type        = number
  default     = 3
}

variable "production_node_vm_size" {
  description = "VM size used by the AKS production workload node pool"
  type        = string
  default     = "Standard_D2s_v3"
}

variable "production_node_count" {
  description = "Initial number of nodes in the AKS production workload node pool"
  type        = number
  default     = 1
}

variable "production_min_node_count" {
  description = "Minimum number of production workload nodes used by the cluster autoscaler"
  type        = number
  default     = 1
}

variable "production_max_node_count" {
  description = "Maximum number of production workload nodes used by the cluster autoscaler"
  type        = number
  default     = 3
}
