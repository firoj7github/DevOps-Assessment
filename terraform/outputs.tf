output "resource_group_name" {
  description = "Name of the created resource group"
  value       = azurerm_resource_group.main.name
}

output "resource_group_location" {
  description = "Location of the resource group"
  value       = azurerm_resource_group.main.location
}

output "vnet_id" {
  description = "VNet resource ID"
  value       = module.networking.vnet_id
}

output "aks_subnet_id" {
  description = "AKS subnet resource ID"
  value       = module.networking.aks_subnet_id
}

output "aks_cluster_name" {
  description = "AKS cluster name"
  value       = module.aks.cluster_name
}

output "aks_cluster_id" {
  description = "AKS cluster resource ID"
  value       = module.aks.cluster_id
}

output "aks_node_resource_group" {
  description = "Auto-created node resource group"
  value       = module.aks.node_resource_group
}

output "acr_name" {
  description = "Azure Container Registry name"
  value       = module.acr.acr_name
}

output "acr_login_server" {
  description = "ACR login server URL (used in docker push/pull)"
  value       = module.acr.acr_login_server
}

output "kubeconfig_command" {
  description = "Run this command to set up kubectl access"
  value       = "az aks get-credentials --resource-group ${azurerm_resource_group.main.name} --name ${module.aks.cluster_name} --overwrite-existing"
}
