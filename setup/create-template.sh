#!/bin/bash
# =============================================================================
# Création automatique du template VM Ubuntu sur Proxmox
# Alternative à Packer pour les configurations réseau NAT
# Utilise l'image cloud Ubuntu (qcow2) au lieu d'une installation ISO
# =============================================================================

set -e

TEMPLATE_ID=9000
TEMPLATE_NAME="ubuntu-k3s-template"
STORAGE="local"
BRIDGE="vmbr1"
CLOUD_IMAGE_URL="https://cloud-images.ubuntu.com/jammy/current/jammy-server-cloudimg-amd64.img"
CLOUD_IMAGE="/tmp/jammy-server-cloudimg-amd64.img"

echo "=== Création du template VM Ubuntu K3s ==="

# Supprimer le template existant si besoin
if qm status $TEMPLATE_ID &>/dev/null; then
    echo "[*] Suppression du template existant (ID $TEMPLATE_ID)..."
    qm destroy $TEMPLATE_ID --purge 2>/dev/null || true
fi

# Télécharger l'image cloud Ubuntu
if [ ! -f "$CLOUD_IMAGE" ]; then
    echo "[1/8] Téléchargement de l'image cloud Ubuntu 22.04..."
    wget -q --show-progress -O "$CLOUD_IMAGE" "$CLOUD_IMAGE_URL"
else
    echo "[1/8] Image cloud déjà présente, skip téléchargement"
fi

# Installer les paquets nécessaires dans l'image (via virt-customize si dispo)
if command -v virt-customize &>/dev/null; then
    echo "[2/8] Pré-installation des paquets dans l'image..."
    virt-customize -a "$CLOUD_IMAGE" \
        --install qemu-guest-agent,curl,wget,gnupg2,software-properties-common,apt-transport-https,ca-certificates,nfs-common,open-iscsi,jq,unzip \
        --run-command 'systemctl enable qemu-guest-agent'
else
    echo "[2/8] Installation de libguestfs-tools pour personnaliser l'image..."
    apt-get update -qq && apt-get install -y -qq libguestfs-tools > /dev/null 2>&1
    echo "[2/8] Pré-installation des paquets dans l'image..."
    virt-customize -a "$CLOUD_IMAGE" \
        --install qemu-guest-agent,curl,wget,gnupg2,software-properties-common,apt-transport-https,ca-certificates,nfs-common,open-iscsi,jq,unzip \
        --run-command 'systemctl enable qemu-guest-agent'
fi

# Redimensionner le disque image
echo "[3/8] Redimensionnement du disque à 30G..."
qemu-img resize "$CLOUD_IMAGE" 30G

# Créer la VM
echo "[4/8] Création de la VM template..."
qm create $TEMPLATE_ID \
    --name "$TEMPLATE_NAME" \
    --description "Ubuntu 22.04 LTS - Template K3s pour MSPR COGIP" \
    --memory 4096 \
    --cores 2 \
    --cpu host \
    --net0 virtio,bridge=$BRIDGE \
    --scsihw virtio-scsi-single \
    --agent enabled=1 \
    --ostype l26 \
    --onboot 0

# Importer le disque
echo "[5/8] Import du disque cloud image..."
qm importdisk $TEMPLATE_ID "$CLOUD_IMAGE" $STORAGE --format qcow2

# Attacher le disque et configurer
echo "[6/8] Configuration de la VM..."
qm set $TEMPLATE_ID --scsi0 ${STORAGE}:${TEMPLATE_ID}/vm-${TEMPLATE_ID}-disk-0.qcow2
qm set $TEMPLATE_ID --ide2 ${STORAGE}:cloudinit
qm set $TEMPLATE_ID --boot order=scsi0
qm set $TEMPLATE_ID --serial0 socket --vga serial0

# Convertir en template
echo "[7/8] Conversion en template Proxmox..."
qm template $TEMPLATE_ID

# Nettoyage
echo "[8/8] Nettoyage..."
rm -f "$CLOUD_IMAGE"

echo ""
echo "=== Template créé avec succès ==="
echo "  ID   : $TEMPLATE_ID"
echo "  Nom  : $TEMPLATE_NAME"
echo "  Vous pouvez maintenant lancer Terraform."
