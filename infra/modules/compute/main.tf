resource "azurerm_linux_virtual_machine" "web" {
  name                = "vm-web"
  computer_name       = "vm-web"
  resource_group_name = var.resource_group_name
  location            = var.location
  size                = "Standard_D2s_v7"
  admin_username      = "azureadmin"

  network_interface_ids = [
    var.network_interface_id
  ]

  disable_password_authentication = true
  provision_vm_agent              = true
  allow_extension_operations      = true

  patch_assessment_mode = "ImageDefault"
  patch_mode            = "ImageDefault"

  disk_controller_type = "NVMe"

  admin_ssh_key {
    username = "azureadmin"
    public_key = trimspace(
      "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPOZlN9tldLqHTZ7ell7+Zd49NHxOy9QQe34b7rHMRRr azure-devops-lab"
    )
  }

  os_disk {
    name                 = "disk-vm-web-os"
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
    disk_size_gb         = 30
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts-gen2"
    version   = "latest"
  }

  boot_diagnostics {}

  identity {
    type = "SystemAssigned"
  }

  tags = {}
}
