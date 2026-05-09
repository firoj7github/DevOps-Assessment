# ACR name must be globally unique, alphanumeric only, 5-50 chars
resource "azurerm_container_registry" "main" {
  # Replace hyphens: ACR name cannot contain hyphens
  name                = replace("${var.name_prefix}acr", "-", "")
  resource_group_name = var.resource_group
  location            = var.location
  sku                 = var.acr_sku
  admin_enabled       = false
  tags                = var.tags
}
