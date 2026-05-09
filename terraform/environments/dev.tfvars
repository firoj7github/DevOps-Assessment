environment            = "dev"
location               = "eastus"
project                = "hydrus"

vnet_address_space     = ["10.0.0.0/16"]
aks_subnet_prefix      = "10.0.1.0/24"

aks_node_count         = 2
aks_min_node_count     = 1
aks_max_node_count     = 3
aks_vm_size            = "Standard_D2s_v3"
aks_kubernetes_version = "1.30"

acr_sku = "Basic"

tags = {
  Owner = "DevOps"
  Team  = "Hydrus"
}
