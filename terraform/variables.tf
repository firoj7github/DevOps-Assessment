variable "environment" {
  description = "Environment name (dev, stage, prod)"
  type        = string

  validation {
    condition     = contains(["dev", "stage", "prod"], var.environment)
    error_message = "environment must be one of: dev, stage, prod."
  }
}

variable "location" {
  description = "Azure region"
  type        = string
  default     = "eastus"
}

variable "project" {
  description = "Project name prefix"
  type        = string
  default     = "hydrus"
}

# Networking
variable "vnet_address_space" {
  description = "VNet address space"
  type        = list(string)
  default     = ["10.0.0.0/16"]
}

variable "aks_subnet_prefix" {
  description = "AKS subnet CIDR"
  type        = string
  default     = "10.0.1.0/24"
}

# AKS
variable "aks_node_count" {
  description = "Default node count"
  type        = number
  default     = 2
}

variable "aks_min_node_count" {
  description = "Minimum nodes for autoscaler"
  type        = number
  default     = 1
}

variable "aks_max_node_count" {
  description = "Maximum nodes for autoscaler"
  type        = number
  default     = 5
}

variable "aks_vm_size" {
  description = "Node VM size"
  type        = string
  default     = "Standard_D2s_v3"
}

variable "aks_kubernetes_version" {
  description = "Kubernetes version"
  type        = string
  default     = "1.30"
}

# ACR
variable "acr_sku" {
  description = "ACR SKU (Basic, Standard, Premium)"
  type        = string
  default     = "Standard"
}

variable "tags" {
  description = "Common tags for all resources"
  type        = map(string)
  default     = {}
}
