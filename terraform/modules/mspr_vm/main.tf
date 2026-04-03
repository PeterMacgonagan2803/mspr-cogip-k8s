resource "proxmox_virtual_environment_vm" "this" {
  name        = var.vm_name
  vm_id       = var.vm_id
  node_name   = var.proxmox_node
  description = var.description
  on_boot     = true
  started     = true

  clone {
    vm_id = var.template_vm_id
    full  = true
  }

  cpu {
    cores   = var.cores
    sockets = 1
    type    = "host"
  }

  memory {
    dedicated = var.memory_mb
  }

  agent {
    enabled = true
  }

  operating_system {
    type = "l26"
  }

  serial_device {}

  disk {
    interface    = "scsi0"
    size         = var.disk_gb
    datastore_id = var.storage_pool
    file_format  = "qcow2"
  }

  network_device {
    bridge = var.network_bridge
    model  = "virtio"
  }

  initialization {
    datastore_id = var.storage_pool

    ip_config {
      ipv4 {
        address = var.ip_address
        gateway = var.gateway
      }
    }
    dns {
      servers = [var.nameserver]
    }
    user_account {
      username = var.ssh_user
      keys     = [var.ssh_public_key]
    }
  }

  lifecycle {
    ignore_changes = [
      network_device,
    ]
  }
}
