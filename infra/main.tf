module "resource_group" {
  source = "./modules/resource-group"

  name     = var.resource_group_name
  location = var.location
  tags     = {}
}

module "network" {
  source = "./modules/network"

  resource_group_name = module.resource_group.name
  location            = module.resource_group.location
}

module "monitoring" {
  source = "./modules/monitoring"

  resource_group_name = module.resource_group.name
  location            = module.resource_group.location
}
