variable "vm_name" {
  type        = string
  description = "Nom de la VM Proxmox"
}

variable "vm_id" {
  type        = number
  description = "VMID Proxmox"
}

variable "cores" {
  type = number
}

variable "memory_mb" {
  type = number
}

variable "disk_gb" {
  type = number
}

variable "ip_address" {
  type        = string
  description = "Adresse IPv4 avec prefixe CIDR"
}

variable "description" {
  type = string
}

variable "proxmox_node" {
  type = string
}

variable "storage_pool" {
  type = string
}

variable "network_bridge" {
  type = string
}

variable "gateway" {
  type = string
}

variable "nameserver" {
  type = string
}

variable "ssh_user" {
  type = string
}

variable "ssh_public_key" {
  type = string
}

variable "template_vm_id" {
  type        = number
  default     = 9000
  description = "VMID du template Packer a cloner"
}
