terraform {
  required_version = ">= 1.5.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.100"
    }
  }

  # Backend config is passed entirely via -backend-config flag at init time.
  # This avoids hardcoding environment-specific values here.
  #
  # Usage:
  #   terraform init -backend-config=environments/dev.backend.hcl
  #   terraform init -backend-config=environments/stage.backend.hcl -reconfigure
  #   terraform init -backend-config=environments/prod.backend.hcl -reconfigure
  backend "azurerm" {}
}

provider "azurerm" {
  features {
    resource_group {
      prevent_deletion_if_contains_resources = false
    }
    key_vault {
      purge_soft_delete_on_destroy = true
    }
  }
}
