output "virtual_machine_id" {
  value = azurerm_linux_virtual_machine.web.id
}

output "virtual_machine_name" {
  value = azurerm_linux_virtual_machine.web.name
}

output "principal_id" {
  value = azurerm_linux_virtual_machine.web.identity[0].principal_id
}
