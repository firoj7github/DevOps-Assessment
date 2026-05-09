environment            = "stage"
location               = "eastus"
project                = "hydrus"

vnet_address_space     = ["10.1.0.0/16"]
aks_subnet_prefix      = "10.1.1.0/24"

aks_node_count         = 2
aks_min_node_count     = 2
aks_max_node_count     = 5
aks_vm_size            = "Standard_D2s_v3"
aks_kubernetes_version = "1.28"

acr_sku = "Standard"

tags = {
  Owner = "DevOps"
  Team  = "Hydrus"
}
