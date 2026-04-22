#!/bin/bash
# Simule un crash du workload Odoo : suppression du pod, recreation par le Deployment.
set -euo pipefail
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
echo "=== Pods avant ==="
sudo kubectl get pods -n odoo -o wide
POD=$(sudo kubectl get pods -n odoo -o name | grep '^pod/odoo-' | grep -v postgresql | head -1 | cut -d/ -f2)
if [ -z "$POD" ]; then echo "ERREUR: aucun pod odoo trouve"; exit 1; fi
echo "=== Suppression pod: $POD ==="
sudo kubectl delete pod -n odoo "$POD" --wait=true
echo "=== Rollout deployment/odoo ==="
sudo kubectl rollout status deployment/odoo -n odoo --timeout=180s
echo "=== Pods apres ==="
sudo kubectl get pods -n odoo -o wide
echo "=== HTTP local (Host odoo.local) ==="
curl -sI -H "Host: odoo.local" --max-time 15 http://127.0.0.1/ | head -1 || true
echo "=== HTTPS local ==="
curl -skI -H "Host: odoo.local" --max-time 15 https://127.0.0.1/ | head -1 || true
echo "=== OK ==="
