# Ordre strict: control-plane -> worker-1 -> worker-2 -> NFS (depends_on entre modules)
# pour limiter la contention disque sur les clones QEMU.

module "k3s_server" {
  source = "./modules/mspr_vm"

  template_vm_id = var.template_vm_id
  vm_name        = "k3s-server"
  vm_id          = 200
  cores          = 2
  memory_mb      = 4096
  disk_gb        = 30
  ip_address     = var.ip_control_plane
  description    = "K3s Control Plane - MSPR COGIP"
  proxmox_node   = var.proxmox_node
  storage_pool   = var.storage_pool
  network_bridge = var.network_bridge
  gateway        = var.gateway
  nameserver     = var.nameserver
  ssh_user       = var.ssh_user
  ssh_public_key = var.ssh_public_key
}

module "k3s_worker_1" {
  source     = "./modules/mspr_vm"
  depends_on = [module.k3s_server]

  template_vm_id = var.template_vm_id
  vm_name        = "k3s-worker-1"
  vm_id          = 201
  cores          = 2
  memory_mb      = 4096
  disk_gb        = 30
  ip_address     = var.ip_worker_1
  description    = "K3s Worker 1 - MSPR COGIP"
  proxmox_node   = var.proxmox_node
  storage_pool   = var.storage_pool
  network_bridge = var.network_bridge
  gateway        = var.gateway
  nameserver     = var.nameserver
  ssh_user       = var.ssh_user
  ssh_public_key = var.ssh_public_key
}

module "k3s_worker_2" {
  source     = "./modules/mspr_vm"
  depends_on = [module.k3s_worker_1]

  template_vm_id = var.template_vm_id
  vm_name        = "k3s-worker-2"
  vm_id          = 202
  cores          = 2
  memory_mb      = 4096
  disk_gb        = 30
  ip_address     = var.ip_worker_2
  description    = "K3s Worker 2 - MSPR COGIP"
  proxmox_node   = var.proxmox_node
  storage_pool   = var.storage_pool
  network_bridge = var.network_bridge
  gateway        = var.gateway
  nameserver     = var.nameserver
  ssh_user       = var.ssh_user
  ssh_public_key = var.ssh_public_key
}

module "nfs_server" {
  source     = "./modules/mspr_vm"
  depends_on = [module.k3s_worker_2]

  template_vm_id = var.template_vm_id
  vm_name        = "nfs-server"
  vm_id          = 203
  cores          = 2
  memory_mb      = 2048
  disk_gb        = 50
  ip_address     = var.ip_nfs
  description    = "Serveur NFS - Stockage persistant K8s"
  proxmox_node   = var.proxmox_node
  storage_pool   = var.storage_pool
  network_bridge = var.network_bridge
  gateway        = var.gateway
  nameserver     = var.nameserver
  ssh_user       = var.ssh_user
  ssh_public_key = var.ssh_public_key
}
