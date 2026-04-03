variable "proxmox_url" {
  type        = string
  description = "URL de l'API Proxmox (ex: https://proxmox.local:8006/api2/json)"
}

variable "proxmox_user" {
  type        = string
  default     = "root@pam"
  description = "Utilisateur Proxmox (ex: root@pam)"
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

variable "template_name" {
  type        = string
  default     = "ubuntu-k3s-template"
  description = "Nom du template VM créé par Packer"
}

variable "storage_pool" {
  type        = string
  default     = "local-lvm"
  description = "Pool de stockage Proxmox"
}

variable "network_bridge" {
  type        = string
  default     = "vmbr0"
  description = "Bridge réseau Proxmox"
}

variable "ssh_public_key" {
  type        = string
  description = "Clé publique SSH pour l'accès aux VMs"
}

variable "ssh_user" {
  type        = string
  default     = "ubuntu"
  description = "Utilisateur SSH des VMs"
}

variable "gateway" {
  type        = string
  description = "Passerelle réseau (ex: 10.0.0.1)"
}

variable "nameserver" {
  type        = string
  default     = "8.8.8.8"
  description = "Serveur DNS"
}

variable "ip_control_plane" {
  type        = string
  description = "Adresse IP du control-plane K3s (ex: 10.0.0.10/24)"
}

variable "ip_worker_1" {
  type        = string
  description = "Adresse IP du worker 1 (ex: 10.0.0.11/24)"
}

variable "ip_worker_2" {
  type        = string
  description = "Adresse IP du worker 2 (ex: 10.0.0.12/24)"
}

variable "ip_nfs" {
  type        = string
  description = "Adresse IP du serveur NFS (ex: 10.0.0.13/24)"
}

variable "ssh_private_key_path" {
  type        = string
  default     = "~/.ssh/id_rsa"
  description = "Chemin vers la clé privée SSH (pour l'inventaire Ansible)"
}

variable "k3s_version" {
  type        = string
  default     = "v1.29.2+k3s1"
  description = "Version de K3s à installer"
}

variable "odoo_domain" {
  type        = string
  default     = "odoo.local"
  description = "Nom de domaine pour l'accès à Odoo"
}

variable "nfs_export_path" {
  type        = string
  default     = "/srv/nfs/k8s"
  description = "Chemin d'export NFS sur le serveur"
}
