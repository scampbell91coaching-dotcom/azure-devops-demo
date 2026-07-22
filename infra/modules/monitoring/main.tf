resource "azurerm_log_analytics_workspace" "main" {
  name                = "law-devops-lab"
  location            = var.location
  resource_group_name = var.resource_group_name
  sku                 = "PerGB2018"
  retention_in_days   = 30

  tags = {
    Environment = "Lab"
    Project     = "Azure DevOps Assessment"
  }
}

resource "azurerm_application_insights" "main" {
  name                = "appi-devops-lab"
  location            = var.location
  resource_group_name = var.resource_group_name
  workspace_id        = azurerm_log_analytics_workspace.main.id
  application_type    = "web"

  tags = {
    Environment = "Lab"
    Project     = "Azure DevOps Assessment"
  }
}
resource "azurerm_virtual_machine_extension" "azure_monitor_agent" {
  name                       = "AzureMonitorLinuxAgent"
  virtual_machine_id         = var.virtual_machine_id
  publisher                  = "Microsoft.Azure.Monitor"
  type                       = "AzureMonitorLinuxAgent"
  type_handler_version       = "1.30"
  auto_upgrade_minor_version = true

  tags = {
    Environment = "Lab"
    Project     = "Azure DevOps Assessment"
  }
}
resource "azurerm_monitor_data_collection_rule" "linux_vm" {
  name                = "dcr-linux-vm"
  resource_group_name = var.resource_group_name
  location            = var.location
  kind                = "Linux"

  destinations {
    log_analytics {
      workspace_resource_id = azurerm_log_analytics_workspace.main.id
      name                  = "log-analytics"
    }
  }

  data_flow {
    streams      = ["Microsoft-Perf", "Microsoft-Syslog"]
    destinations = ["log-analytics"]
  }

  data_sources {
    performance_counter {
      name                          = "perfCounters"
      streams                       = ["Microsoft-Perf"]
      sampling_frequency_in_seconds = 60

      counter_specifiers = [
        "\\Processor(_Total)\\% Processor Time",
        "\\Memory\\Available MBytes",
        "\\Logical Disk(*)\\% Free Space"
      ]
    }

    syslog {
      name           = "syslogData"
      streams        = ["Microsoft-Syslog"]
      facility_names = ["*"]
      log_levels = [
        "Warning",
        "Error",
        "Critical",
        "Alert",
        "Emergency"
      ]
    }
  }

  tags = {
    Environment = "Lab"
    Project     = "Azure DevOps Assessment"
  }
}

resource "azurerm_monitor_data_collection_rule_association" "linux_vm" {
  name                    = "dcra-linux-vm"
  target_resource_id      = var.virtual_machine_id
  data_collection_rule_id = azurerm_monitor_data_collection_rule.linux_vm.id

  description = "Associate VM with Linux DCR"
}
