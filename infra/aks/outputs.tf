output "aks_cluster_name" {
  description = "AKS cluster name"
  value       = azurerm_kubernetes_cluster.aks.name
}

output "aks_resource_group_name" {
  description = "AKS resource group"
  value       = azurerm_kubernetes_cluster.aks.resource_group_name
}

output "aks_node_resource_group" {
  description = "Azure-managed resource group containing AKS infrastructure"
  value       = azurerm_kubernetes_cluster.aks.node_resource_group
}

output "kubelet_identity_object_id" {
  description = "Object ID of the AKS kubelet managed identity"
  value       = azurerm_kubernetes_cluster.aks.kubelet_identity[0].object_id
}

output "log_analytics_workspace_id" {
  description = "ID of the existing Log Analytics workspace used by AKS monitoring"
  value       = data.azurerm_log_analytics_workspace.aks.id
}

output "get_credentials_command" {
  description = "Command used to configure kubectl"
  value       = "az aks get-credentials --resource-group ${azurerm_kubernetes_cluster.aks.resource_group_name} --name ${azurerm_kubernetes_cluster.aks.name} --overwrite-existing"
}
