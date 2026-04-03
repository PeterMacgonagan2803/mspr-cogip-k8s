resource "local_file" "ansible_inventory" {
  content = templatefile("${path.module}/templates/hosts.yml.tftpl", {
    ssh_user        = var.ssh_user
    ssh_key_path    = var.ssh_private_key_path
    k3s_version     = var.k3s_version
    odoo_domain     = var.odoo_domain
    cp_ip           = split("/", var.ip_control_plane)[0]
    worker1_ip      = split("/", var.ip_worker_1)[0]
    worker2_ip      = split("/", var.ip_worker_2)[0]
    nfs_ip          = split("/", var.ip_nfs)[0]
    nfs_export_path = var.nfs_export_path
  })
  filename = "${path.module}/../ansible/inventory/hosts.yml"

  depends_on = [
    module.k3s_server,
    module.k3s_worker_1,
    module.k3s_worker_2,
    module.nfs_server,
  ]
}
