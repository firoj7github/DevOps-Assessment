variable "name_prefix" {
  type = string
}
variable "resource_group" {
  type = string
}
variable "location" {
  type = string
}
variable "acr_sku" {
  type    = string
  default = "Standard"
}
variable "tags" {
  type    = map(string)
  default = {}
}
