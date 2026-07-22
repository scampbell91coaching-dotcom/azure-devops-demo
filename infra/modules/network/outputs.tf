output "virtual_network_id" {
  description = "Resource ID of the virtual network."
  value       = azurerm_virtual_network.main.id
}

output "web_subnet_id" {
  description = "Resource ID of the web subnet."
  value       = azurerm_subnet.web.id
}

output "database_subnet_id" {
  description = "Resource ID of the database subnet."
  value       = azurerm_subnet.database.id
}

output "web_network_security_group_id" {
  description = "Resource ID of the web network security group."
  value       = azurerm_network_security_group.web.id
}

output "public_ip_id" {
  description = "Resource ID of the web public IP."
  value       = azurerm_public_ip.web.id
}

output "public_ip_address" {
  description = "Public IP address assigned to the web server."
  value       = azurerm_public_ip.web.ip_address
}

output "network_interface_id" {
  description = "Resource ID of the web network interface."
  value       = azurerm_network_interface.web.id
}
