#!/bin/bash
# A lancer sur le serveur Proxmox en root (Packer + HTTP sur 10.10.10.1).
# Usage:
#   export PROXMOX_PASSWORD='...'
#   export PROXMOX_NODE='ns3139245'
#   ./run-on-proxmox.sh [vm_id]
set -euo pipefail
VM_ID="${1:-9002}"
REPO="${MSPR_REPO:-/root/mspr-cogip-k8s}"

cd "$REPO"
git fetch origin
git reset --hard origin/main

HASH=$(openssl passwd -6 ubuntu)
sed -i "s|__UBUNTU_HASH__|${HASH}|" packer/http/user-data

qm stop "$VM_ID" --timeout 15 2>/dev/null || true
sleep 2
qm destroy "$VM_ID" --purge 2>/dev/null || true

cd packer
packer init .

export PACKER_LOG=1
export PACKER_LOG_PATH="/tmp/packer-${VM_ID}-$(date +%s).log"

packer build \
  -var "proxmox_password=${PROXMOX_PASSWORD:?set PROXMOX_PASSWORD}" \
  -var "proxmox_node=${PROXMOX_NODE:?set PROXMOX_NODE}" \
  -var "vm_id=${VM_ID}" \
  .

echo "Log Packer: $PACKER_LOG_PATH"
qm list | grep "$VM_ID" || true
