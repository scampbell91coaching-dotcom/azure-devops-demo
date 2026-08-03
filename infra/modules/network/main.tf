resource "azurerm_virtual_network" "main" {
  name                = "vnet-devops-lab"
  location            = var.location
  resource_group_name = var.resource_group_name

  address_space = [
    "10.0.0.0/16"
  ]
}

resource "azurerm_subnet" "database" {
  name                 = "snet-database"
  resource_group_name  = var.resource_group_name
  virtual_network_name = azurerm_virtual_network.main.name

  address_prefixes = [
    "10.0.2.0/24"
  ]

  dynamic "delegation" {
    for_each = var.enable_postgresql_delegation ? [1] : []

    content {
      name = "postgresql-flexible-server"

      service_delegation {
        name = "Microsoft.DBforPostgreSQL/flexibleServers"
        actions = [
          "Microsoft.Network/virtualNetworks/subnets/join/action",
        ]
      }
    }
  }
}
