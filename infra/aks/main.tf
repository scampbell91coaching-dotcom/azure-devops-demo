data "azurerm_resource_group" "lab" {
  name = var.resource_group_name
}

data "azurerm_container_registry" "acr" {
  name                = var.acr_name
  resource_group_name = var.resource_group_name
}

data "azurerm_log_analytics_workspace" "aks" {
  name                = var.log_analytics_workspace_name
  resource_group_name = var.resource_group_name
}

resource "azurerm_kubernetes_cluster" "aks" {
  # checkov:skip=CKV_AZURE_115:Private AKS is deferred until private DNS, runner connectivity and operator access are designed and tested.
  # checkov:skip=CKV_AZURE_117:Customer-managed disk encryption is deferred until Key Vault, key rotation and identity permissions are implemented.
  oidc_issuer_enabled          = true
  workload_identity_enabled    = true
  azure_policy_enabled         = true
  local_account_disabled       = true
  image_cleaner_enabled        = true
  image_cleaner_interval_hours = 48
  automatic_upgrade_channel    = "patch"
  node_os_upgrade_channel      = "NodeImage"
  name                         = var.aks_name
  location                     = data.azurerm_resource_group.lab.location
  resource_group_name          = data.azurerm_resource_group.lab.name
  dns_prefix                   = var.dns_prefix

  sku_tier = "Standard"

  api_server_access_profile {
    authorized_ip_ranges = var.api_server_authorized_ip_ranges
  }

  default_node_pool {
    name                         = "system"
    vm_size                      = var.node_vm_size
    node_count                   = var.node_count
    auto_scaling_enabled         = false
    max_pods                     = 50
    only_critical_addons_enabled = true
    temporary_name_for_rotation  = "systemtemp"

    os_disk_size_gb         = 30
    os_disk_type            = "Ephemeral"
    host_encryption_enabled = true
    os_sku                  = "AzureLinux"
    type                    = "VirtualMachineScaleSets"

    upgrade_settings {
      max_surge = "10%"
    }
  }

  key_vault_secrets_provider {
    secret_rotation_enabled  = true
    secret_rotation_interval = "2m"
  }

  identity {
    type = "SystemAssigned"
  }

  oms_agent {
    log_analytics_workspace_id = data.azurerm_log_analytics_workspace.aks.id
  }

  network_profile {
    network_plugin    = "azure"
    network_policy    = "azure"
    load_balancer_sku = "standard"
    outbound_type     = "loadBalancer"
  }

  role_based_access_control_enabled = true

  tags = {
    Environment = "lab"
    Project     = "azure-devops-demo"
    ManagedBy   = "terraform"
  }
}

resource "azurerm_role_assignment" "aks_acr_pull" {
  scope                = data.azurerm_container_registry.acr.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_kubernetes_cluster.aks.kubelet_identity[0].object_id

  depends_on = [
    azurerm_kubernetes_cluster.aks
  ]
}
