output "virtual_network_id" {
  description = "Resource ID of the virtual network."
  value       = azurerm_virtual_network.main.id
}

output "virtual_network_name" {
  description = "Name of the application virtual network."
  value       = azurerm_virtual_network.main.name
}

output "database_subnet_id" {
  description = "Resource ID of the database subnet."
  value       = azurerm_subnet.database.id
}
