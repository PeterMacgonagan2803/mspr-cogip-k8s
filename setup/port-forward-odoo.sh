#!/bin/bash
# =============================================================================
# Port-forwarding pour accéder à Odoo depuis l'extérieur
# Exécuter en root sur le serveur Proxmox
# =============================================================================
# Redirige le trafic HTTPS (443) et HTTP (80) de l'IP publique vers le
# control-plane K3s (10.10.10.10) où Traefik écoute.
# =============================================================================

CONTROL_PLANE_IP="10.10.10.10"

echo "=== Mise en place du port-forwarding vers Odoo ==="

# HTTPS (443)
iptables -t nat -A PREROUTING -i vmbr0 -p tcp --dport 443 -j DNAT --to-destination ${CONTROL_PLANE_IP}:443
echo "[OK] Port 443 (HTTPS) → ${CONTROL_PLANE_IP}:443"

# HTTP (80) → redirigé vers HTTPS par Traefik
iptables -t nat -A PREROUTING -i vmbr0 -p tcp --dport 80 -j DNAT --to-destination ${CONTROL_PLANE_IP}:80
echo "[OK] Port 80 (HTTP) → ${CONTROL_PLANE_IP}:80"

# kubectl API (optionnel, pour administrer depuis l'extérieur)
iptables -t nat -A PREROUTING -i vmbr0 -p tcp --dport 6443 -j DNAT --to-destination ${CONTROL_PLANE_IP}:6443
echo "[OK] Port 6443 (K8s API) → ${CONTROL_PLANE_IP}:6443"

# Rendre les règles persistantes
apt-get install -y iptables-persistent 2>/dev/null
netfilter-persistent save 2>/dev/null

echo ""
echo "=== Port-forwarding actif ==="
echo "Odoo accessible via : https://<IP_PUBLIQUE_OVH>"
echo "K8s API via          : https://<IP_PUBLIQUE_OVH>:6443"
