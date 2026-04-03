output "control_plane_ip" {
  description = "Adresse IP du control-plane K3s"
  value       = split("/", var.ip_control_plane)[0]
}

output "worker_1_ip" {
  description = "Adresse IP du worker 1"
  value       = split("/", var.ip_worker_1)[0]
}

output "worker_2_ip" {
  description = "Adresse IP du worker 2"
  value       = split("/", var.ip_worker_2)[0]
}

output "nfs_server_ip" {
  description = "Adresse IP du serveur NFS"
  value       = split("/", var.ip_nfs)[0]
}

output "vm_info" {
  description = "Informations sur les VMs deployees"
  value = {
    "k3s-server"   = { id = module.k3s_server.vm_id, name = module.k3s_server.name }
    "k3s-worker-1" = { id = module.k3s_worker_1.vm_id, name = module.k3s_worker_1.name }
    "k3s-worker-2" = { id = module.k3s_worker_2.vm_id, name = module.k3s_worker_2.name }
    "nfs-server"   = { id = module.nfs_server.vm_id, name = module.nfs_server.name }
  }
}
