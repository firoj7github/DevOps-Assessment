environment            = "prod"
location               = "eastus"
project                = "hydrus"

vnet_address_space     = ["10.2.0.0/16"]
aks_subnet_prefix      = "10.2.1.0/24"

aks_node_count         = 3
aks_min_node_count     = 3
aks_max_node_count     = 10
aks_vm_size            = "Standard_D4s_v3"
aks_kubernetes_version = "1.30"

acr_sku = "Premium"

tags = {
  Owner = "DevOps"
  Team  = "Hydrus"
}
