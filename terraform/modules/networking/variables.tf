variable "name_prefix" {
  type = string
}
variable "resource_group" {
  type = string
}
variable "location" {
  type = string
}
variable "vnet_address_space" {
  type = list(string)
}
variable "aks_subnet_prefix" {
  type = string
}
variable "tags" {
  type    = map(string)
  default = {}
}
