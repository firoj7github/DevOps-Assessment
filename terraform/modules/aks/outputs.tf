output "cluster_id" {
  value = azurerm_kubernetes_cluster.main.id
}
output "cluster_name" {
  value = azurerm_kubernetes_cluster.main.name
}
output "node_resource_group" {
  value = azurerm_kubernetes_cluster.main.node_resource_group
}
output "kube_config_raw" {
  value     = azurerm_kubernetes_cluster.main.kube_config_raw
  sensitive = true
}
output "log_analytics_workspace_id" {
  value = azurerm_log_analytics_workspace.main.id
}
