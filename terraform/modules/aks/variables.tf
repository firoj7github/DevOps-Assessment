variable "name_prefix" {
  type = string
}
variable "resource_group" {
  type = string
}
variable "location" {
  type = string
}
variable "kubernetes_version" {
  type    = string
  default = "1.28"
}
variable "node_count" {
  type    = number
  default = 2
}
variable "min_node_count" {
  type    = number
  default = 1
}
variable "max_node_count" {
  type    = number
  default = 5
}
variable "vm_size" {
  type    = string
  default = "Standard_D2s_v3"
}
variable "aks_subnet_id" {
  type = string
}
variable "acr_id" {
  type = string
}
variable "tags" {
  type    = map(string)
  default = {}
}
