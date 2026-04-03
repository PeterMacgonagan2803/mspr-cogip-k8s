packer {
  required_plugins {
    proxmox = {
      version = ">= 1.1.6"
      source  = "github.com/hashicorp/proxmox"
    }
  }
}

source "proxmox-iso" "ubuntu-k3s" {
  proxmox_url              = var.proxmox_url
  username                 = var.proxmox_username
  password                 = var.proxmox_password
  insecure_skip_tls_verify = true
  node                     = var.proxmox_node

  iso_file    = var.iso_file
  unmount_iso = true

  vm_id                = var.vm_id
  vm_name              = "ubuntu-k3s-template"
  template_description = "Ubuntu 22.04 LTS - Template K3s pour MSPR COGIP (via Packer)"

  os          = "l26"
  cpu_type    = "host"
  cores       = 2
  memory      = 4096
  qemu_agent  = true

  scsi_controller = "virtio-scsi-single"

  disks {
    type         = "scsi"
    disk_size    = "30G"
    storage_pool = var.storage_pool
    format       = "qcow2"
  }

  network_adapters {
    model    = "virtio"
    bridge   = var.network_bridge
    firewall = false
  }

  http_directory    = "http"
  http_bind_address = "10.10.10.1"

  boot_command = [
    "c<wait3>",
    "linux /casper/vmlinuz --- autoinstall ip=10.10.10.99::10.10.10.1:255.255.255.0:ubuntu-k3s::off:8.8.8.8:8.8.4.4 ds=nocloud-net\\;s=http://{{ .HTTPIP }}:{{ .HTTPPort }}/<enter><wait3>",
    "initrd /casper/initrd<enter><wait3>",
    "boot<enter>"
  ]

  boot_wait = "5s"

  ssh_username = var.ssh_username
  ssh_password = var.ssh_password
  ssh_timeout  = "120m"
  ssh_host     = "10.10.10.99"
}

build {
  sources = ["source.proxmox-iso.ubuntu-k3s"]

  provisioner "shell" {
    inline = [
      "echo 'Attente fin des verrous apt (unattended-upgrades au premier boot)...'",
      "bash -c 'for n in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32 33 34 35 36 37 38 39 40 41 42 43 44 45 46 47 48 49 50 51 52 53 54 55 56 57 58 59 60; do fuser /var/lib/dpkg/lock /var/lib/apt/lists/lock /var/cache/apt/archives/lock >/dev/null 2>&1 || exit 0; echo attente verrou apt; sleep 5; done'",
      "sudo DEBIAN_FRONTEND=noninteractive apt-get update -qq"
    ]
  }

  # apt-get install peut recharger ssh/pam et couper la session (erreur Packer 2300218).
  provisioner "shell" {
    expect_disconnect = true
    inline = [
      "sudo DEBIAN_FRONTEND=noninteractive apt-get install -y qemu-guest-agent curl wget gnupg2 software-properties-common apt-transport-https ca-certificates nfs-common open-iscsi jq unzip"
    ]
  }

  provisioner "shell" {
    inline = [
      "sudo DEBIAN_FRONTEND=noninteractive apt-get install -y qemu-guest-agent curl wget gnupg2 software-properties-common apt-transport-https ca-certificates nfs-common open-iscsi jq unzip",
      "sudo systemctl enable qemu-guest-agent",

      "echo '=== Suppression snapd (bloque le boot 5-10min via snapd.seeded.service) ==='",
      "sudo systemctl disable snapd.service snapd.socket snapd.seeded.service 2>/dev/null || true",
      "sudo DEBIAN_FRONTEND=noninteractive apt-get purge -y snapd 2>/dev/null || true",
      "sudo apt-mark hold snapd 2>/dev/null || true",
      "sudo rm -rf /snap /var/snap /var/lib/snapd /var/cache/snapd /home/*/.snap",

      "sudo DEBIAN_FRONTEND=noninteractive apt-get autoremove -y",
      "sudo DEBIAN_FRONTEND=noninteractive apt-get clean",
      "sudo rm -f /etc/netplan/*.yaml /etc/netplan/*.yml",

      "echo '=== Nettoyage GRUB (supprime ip= et ds=nocloud-net laisses par autoinstall) ==='",
      "sudo sed -i 's|^GRUB_CMDLINE_LINUX=.*|GRUB_CMDLINE_LINUX=\"\"|' /etc/default/grub",
      "sudo sed -i 's|^GRUB_CMDLINE_LINUX_DEFAULT=.*|GRUB_CMDLINE_LINUX_DEFAULT=\"quiet\"|' /etc/default/grub",
      "grep GRUB_CMDLINE /etc/default/grub",
      "sudo update-grub",

      "sudo cloud-init clean --logs",
      "sudo truncate -s 0 /etc/machine-id"
    ]
  }
}
