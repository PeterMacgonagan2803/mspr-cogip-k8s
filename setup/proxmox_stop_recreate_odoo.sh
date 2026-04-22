#!/bin/bash
# A executer sur Proxmox en root : desinstalle Odoo (Helm), attend 2 min, redeploie via Ansible.
set -euo pipefail
KEY=/root/.ssh/id_ansible
CP=ubuntu@10.10.10.10

echo "=== Helm uninstall odoo (arret release) ==="
ssh -o StrictHostKeyChecking=no -o BatchMode=yes -i "$KEY" "$CP" bash -s <<'EOC'
set -euo pipefail
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
if sudo helm status odoo -n odoo >/dev/null 2>&1; then
  sudo helm uninstall odoo -n odoo --wait --timeout 15m
fi
while read -r s; do
  [ -z "$s" ] && continue
  sudo kubectl delete -n odoo "$s" 2>/dev/null || true
done < <(sudo kubectl get secrets -n odoo -o name 2>/dev/null | grep helm || true)
echo "Pods restants dans odoo :"
sudo kubectl get pods -n odoo 2>/dev/null || true
EOC

echo "=== Pause 120 secondes ==="
sleep 120

echo "=== Ansible deploy-odoo ==="
cd /root/mspr-cogip-k8s/ansible
ansible-playbook playbooks/deploy-odoo.yml -v

echo "=== Termine ==="
