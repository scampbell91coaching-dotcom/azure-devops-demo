terraform {
  backend "azurerm" {
    resource_group_name  = "rg-devops-assessment-lab"
    storage_account_name = "stevedevopslab001"
    container_name       = "tfstate"
    key                  = "terraform.tfstate"

    use_azuread_auth = true
    use_cli          = true

    tenant_id       = "74d2fd2d-dd77-4db5-949c-232b3f50d865"
    subscription_id = "abac1d73-0524-4172-a292-64f8a7595728"
  }
}
