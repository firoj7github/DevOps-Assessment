locals {
  name_prefix = "${var.project}-${var.environment}"
  common_tags = merge(var.tags, {
    Environment = var.environment
    Project     = var.project
    ManagedBy   = "Terraform"
  })
}

# ── Resource Group ─────────────────────────────────────────────────────────────
resource "azurerm_resource_group" "main" {
  name     = "${local.name_prefix}-rg"
  location = var.location
  tags     = local.common_tags
}

# ── Networking ─────────────────────────────────────────────────────────────────
module "networking" {
  source = "./modules/networking"

  name_prefix        = local.name_prefix
  resource_group     = azurerm_resource_group.main.name
  location           = azurerm_resource_group.main.location
  vnet_address_space = var.vnet_address_space
  aks_subnet_prefix  = var.aks_subnet_prefix
  tags               = local.common_tags
}

# ── Azure Container Registry ───────────────────────────────────────────────────
module "acr" {
  source = "./modules/acr"

  name_prefix    = local.name_prefix
  resource_group = azurerm_resource_group.main.name
  location       = azurerm_resource_group.main.location
  acr_sku        = var.acr_sku
  tags           = local.common_tags
}

# ── AKS Cluster ────────────────────────────────────────────────────────────────
module "aks" {
  source = "./modules/aks"

  name_prefix            = local.name_prefix
  resource_group         = azurerm_resource_group.main.name
  location               = azurerm_resource_group.main.location
  kubernetes_version     = var.aks_kubernetes_version
  node_count             = var.aks_node_count
  min_node_count         = var.aks_min_node_count
  max_node_count         = var.aks_max_node_count
  vm_size                = var.aks_vm_size
  aks_subnet_id          = module.networking.aks_subnet_id
  acr_id                 = module.acr.acr_id
  tags                   = local.common_tags
}
