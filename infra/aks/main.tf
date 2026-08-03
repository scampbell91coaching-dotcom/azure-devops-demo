data "azurerm_resource_group" "lab" {
  name = var.resource_group_name
}

data "azurerm_container_registry" "acr" {
  name                = var.acr_name
  resource_group_name = var.resource_group_name
}

resource "azurerm_kubernetes_cluster" "aks" {
  oidc_issuer_enabled       = true
  workload_identity_enabled = true
  name                      = var.aks_name
  location                  = data.azurerm_resource_group.lab.location
  resource_group_name       = data.azurerm_resource_group.lab.name
  dns_prefix                = var.dns_prefix

  sku_tier = "Free"

  api_server_access_profile {
    authorized_ip_ranges = var.api_server_authorized_ip_ranges
  }

  default_node_pool {
    name                 = "system"
    vm_size              = var.node_vm_size
    node_count           = var.node_count
    auto_scaling_enabled = false

    os_disk_size_gb = 30
    type            = "VirtualMachineScaleSets"

    upgrade_settings {
      max_surge = "10%"
    }
  }

  key_vault_secrets_provider {
    secret_rotation_enabled = false
  }

  identity {
    type = "SystemAssigned"
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
