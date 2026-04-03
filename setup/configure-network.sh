#!/bin/bash
# =============================================================================
# Configuration réseau Proxmox pour OVH (IP publique unique + NAT)
# Exécuter en root sur le serveur Proxmox via SSH
# =============================================================================
#
# Ce script crée un bridge interne (vmbr1) avec NAT pour les VMs.
# Les VMs auront des IPs en 10.10.10.x et accèderont à internet via NAT.
#
# Adapter les variables ci-dessous avant exécution !
# =============================================================================

set -e

# ===== VARIABLES A ADAPTER =====
PUBLIC_INTERFACE="eno1"       # Interface réseau publique (vérifier avec: ip a)
PUBLIC_IP=""                  # Ex. IP publique fournie par votre hebergeur
PUBLIC_GW=""                  # Gateway (souvent x.x.x.254 chez OVH)
INTERNAL_SUBNET="10.10.10"   # Sous-réseau interne pour les VMs
# ================================

if [ -z "$PUBLIC_IP" ] || [ -z "$PUBLIC_GW" ]; then
    echo "ERREUR: Remplis PUBLIC_IP et PUBLIC_GW avant d'exécuter ce script !"
    echo "  PUBLIC_IP  = ton IP publique OVH (visible dans le manager OVH)"
    echo "  PUBLIC_GW  = la gateway OVH (généralement ton IP avec .254 à la fin)"
    exit 1
fi

echo "=== Configuration réseau Proxmox pour MSPR COGIP ==="
echo "Interface publique : $PUBLIC_INTERFACE"
echo "IP publique        : $PUBLIC_IP"
echo "Gateway            : $PUBLIC_GW"
echo "Sous-réseau VMs    : ${INTERNAL_SUBNET}.0/24"
echo ""

# Backup de la config actuelle
cp /etc/network/interfaces /etc/network/interfaces.backup.$(date +%Y%m%d%H%M%S)
echo "[OK] Backup de /etc/network/interfaces créé"

# Écriture de la nouvelle configuration
cat > /etc/network/interfaces << EOF
# =============================================================================
# Configuration réseau Proxmox - MSPR COGIP
# Auto-généré par setup/configure-network.sh
# =============================================================================

auto lo
iface lo inet loopback

# Interface publique
auto ${PUBLIC_INTERFACE}
iface ${PUBLIC_INTERFACE} inet manual

# Bridge public (accès internet Proxmox)
auto vmbr0
iface vmbr0 inet static
    address ${PUBLIC_IP}/24
    gateway ${PUBLIC_GW}
    bridge-ports ${PUBLIC_INTERFACE}
    bridge-stp off
    bridge-fd 0

# Bridge interne (réseau VMs avec NAT)
auto vmbr1
iface vmbr1 inet static
    address ${INTERNAL_SUBNET}.1/24
    bridge-ports none
    bridge-stp off
    bridge-fd 0
    post-up   echo 1 > /proc/sys/net/ipv4/ip_forward
    post-up   iptables -t nat -A POSTROUTING -s ${INTERNAL_SUBNET}.0/24 -o vmbr0 -j MASQUERADE
    post-down iptables -t nat -D POSTROUTING -s ${INTERNAL_SUBNET}.0/24 -o vmbr0 -j MASQUERADE
EOF

echo "[OK] /etc/network/interfaces mis à jour"

# Activer l'IP forwarding de manière persistante
echo "net.ipv4.ip_forward=1" > /etc/sysctl.d/99-ip-forward.conf
sysctl -p /etc/sysctl.d/99-ip-forward.conf
echo "[OK] IP forwarding activé"

echo ""
echo "=== Configuration terminée ==="
echo ""
echo "IMPORTANT : Redémarre le réseau avec :"
echo "  systemctl restart networking"
echo ""
echo "Ou reboot le serveur si tu préfères :"
echo "  reboot"
echo ""
echo "Après redémarrage, les VMs utiliseront :"
echo "  - Bridge    : vmbr1"
echo "  - Gateway   : ${INTERNAL_SUBNET}.1"
echo "  - DNS       : 8.8.8.8"
echo "  - IPs VMs   :"
echo "    k3s-server   : ${INTERNAL_SUBNET}.10/24"
echo "    k3s-worker-1 : ${INTERNAL_SUBNET}.11/24"
echo "    k3s-worker-2 : ${INTERNAL_SUBNET}.12/24"
echo "    nfs-server   : ${INTERNAL_SUBNET}.13/24"
echo ""
echo "Pour accéder à Odoo depuis l'extérieur, ajoute une règle de port-forwarding :"
echo "  iptables -t nat -A PREROUTING -i vmbr0 -p tcp --dport 443 -j DNAT --to-destination ${INTERNAL_SUBNET}.10:443"
echo "  iptables -t nat -A PREROUTING -i vmbr0 -p tcp --dport 80 -j DNAT --to-destination ${INTERNAL_SUBNET}.10:80"
