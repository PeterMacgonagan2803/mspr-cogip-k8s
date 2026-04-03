variable "proxmox_url" {
  type        = string
  default     = "https://127.0.0.1:8006/api2/json"
  description = "URL de l'API Proxmox (localhost quand Packer tourne sur le serveur)"
}

variable "proxmox_username" {
  type        = string
  default     = "root@pam"
  description = "Utilisateur Proxmox"
}

variable "proxmox_password" {
  type        = string
  sensitive   = true
  description = "Mot de passe Proxmox"
}

variable "proxmox_node" {
  type        = string
  description = "Nom du noeud Proxmox cible"
}

variable "iso_file" {
  type        = string
  default     = "local:iso/ubuntu-22.04.5-live-server-amd64.iso"
  description = "Chemin de l'ISO Ubuntu sur le stockage Proxmox"
}

variable "vm_id" {
  type        = number
  default     = 9000
  description = "ID du template VM dans Proxmox"
}

variable "storage_pool" {
  type        = string
  default     = "local"
  description = "Pool de stockage Proxmox (type dir pour qcow2)"
}

variable "network_bridge" {
  type        = string
  default     = "vmbr1"
  description = "Bridge reseau prive NAT"
}

variable "ssh_username" {
  type        = string
  default     = "ubuntu"
  description = "Utilisateur SSH cree par autoinstall"
}

variable "ssh_password" {
  type        = string
  default     = "ubuntu"
  sensitive   = true
  description = "Mot de passe SSH temporaire (remplace par cle SSH via cloud-init au clonage)"
}
