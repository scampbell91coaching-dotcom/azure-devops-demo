subscription_id              = "abac1d73-0524-4172-a292-64f8a7595728"
resource_group_name          = "rg-devops-assessment-lab"
location                     = "eastus2"
aks_name                     = "aks-devops-lab"
dns_prefix                   = "aks-devops-lab"
acr_name                     = "stevedevopslab6280"
log_analytics_workspace_name = "law-devops-lab"

node_vm_size = "Standard_D2s_v3"

node_count     = 2
min_node_count = 1
max_node_count = 1
api_server_authorized_ip_ranges = [
  " 51.6.97.140",
]
