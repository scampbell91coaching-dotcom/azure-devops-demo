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

module "compute" {
  source = "./modules/compute"

  resource_group_name  = module.resource_group.name
  location             = module.resource_group.location
  network_interface_id = module.network.network_interface_id
}

module "monitoring" {
  source = "./modules/monitoring"

  resource_group_name = module.resource_group.name
  location            = module.resource_group.location
  virtual_machine_id  = module.compute.virtual_machine_id
}
