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
    condition     = length(var.api_server_authorized_ip_ranges) > 0
    error_message = "At least one trusted AKS API server CIDR must be supplied."
  }
}

variable "acr_name" {
  description = "Existing Azure Container Registry name"
  type        = string
  default     = "stevedevopslab6280"
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
