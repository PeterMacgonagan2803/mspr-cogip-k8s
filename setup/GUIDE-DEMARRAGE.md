# Guide de demarrage -- Serveur OVH + Proxmox

Ce guide detaille chaque etape pour deployer l'infrastructure MSPR COGIP sur un serveur dedie OVH avec Proxmox VE. A la fin, l'ERP Odoo sera accessible via `http://odoo.local`.

## Checklist complete (dans l'ordre)

- [ ] **Etape 0** -- Installer les outils sur le PC local
- [ ] **Etape 1** -- Premier acces a Proxmox et configuration de base
- [ ] **Etape 2** -- Configurer le reseau Proxmox (NAT vmbr1)
- [ ] **Etape 3** -- Generer une paire de cles SSH
- [ ] **Etape 4** -- Remplir les fichiers de configuration (tfvars + vault)
- [ ] **Etape 5** -- Creer le template VM (image cloud Ubuntu)
- [ ] **Etape 6** -- Lancer Terraform (deployer les 4 VMs)
- [ ] **Etape 7** -- Lancer Ansible (cluster K3s + Odoo)
- [ ] **Etape 8** -- Port-forwarding NAT + fichier hosts + acceder a Odoo
- [ ] **Alternative** -- Deploiement automatique complet (`mspr-deploiement-complet.ps1` ou `deploy-all.py`)

---

## Etape 0 : Installer les outils sur le PC local

Le script `install-tools.ps1` installe tous les prerequis sur Windows.

```powershell
# Ouvrir PowerShell en tant qu'administrateur
cd C:\Users\PC-HUGO\MSPR\setup
.\install-tools.ps1
```

**Outils installes :**
- Terraform >= 1.5 (provisionnement IaC)
- Helm >= 3.12 (deploiement Kubernetes)
- kubectl (client Kubernetes)
- Python 3 + Paramiko (orchestration SSH distante)

**Verification :**
```powershell
terraform --version      # >= 1.5.x
helm version             # >= 3.12.x
kubectl version --client # v1.29+
python --version         # >= 3.10
pip show paramiko        # Paramiko installe
```

> **Note** : Ansible n'est PAS necessaire sur le PC local. Il sera installe et execute directement sur le serveur Proxmox (plus proche des VMs sur le reseau interne).

---

## Etape 1 : Premier acces a Proxmox

### 1.1 Connexion a l'interface web

Ouvrir un navigateur et acceder a :
```
https://<IP-SERVEUR-OVH>:8006
```

Identifiants par defaut OVH : `root` + le mot de passe defini lors de la commande du serveur.

### 1.2 Informations a noter

Ces informations seront necessaires pour la suite :

| Information | Exemple | Ou la trouver |
|-------------|---------|---------------|
| **IP publique** | `VOTRE_IP_PUBLIQUE` | Email OVH ou `ip a show vmbr0` |
| **Nom du noeud** | `ns3139245` | Coin superieur gauche dans Proxmox |
| **Pool de stockage** | `local` | Datacenter > Storage (type `dir`) |
| **Mot de passe root** | `*****` | Defini a la commande OVH |

### 1.3 Verifier le stockage

```bash
ssh root@<IP-SERVEUR-OVH>
pvesm status
```

Le stockage `local` (type `dir`) doit etre present. Si seul `local-lvm` existe, il faudra adapter le `storage_pool` dans les variables Terraform.

---

## Etape 2 : Configurer le reseau Proxmox (NAT)

Avec une seule IP publique OVH, les VMs doivent etre sur un reseau prive interne et acceder a internet via NAT.

### 2.1 Executer le script de configuration

```bash
ssh root@<IP-SERVEUR-OVH>

# Telecharger et executer le script
curl -fsSL https://raw.githubusercontent.com/VOTRE_ORGANISATION/mspr-cogip-k8s/main/setup/configure-network.sh -o /root/configure-network.sh
bash /root/configure-network.sh
```

### 2.2 Ce que fait le script

1. Cree le bridge `vmbr1` avec l'adresse `10.10.10.1/24` (reseau prive des VMs)
2. Active le forwarding IP (`net.ipv4.ip_forward = 1`)
3. Configure les regles iptables NAT MASQUERADE pour que les VMs accedent a internet
4. Redemarre le service reseau Proxmox

### 2.3 Verification

```bash
ip a show vmbr1
# Doit afficher 10.10.10.1/24

iptables -t nat -L POSTROUTING -v -n
# Doit contenir MASQUERADE pour 10.10.10.0/24
```

### 2.4 Plan d'adressage IP

| VM | IP | VMID | Role |
|----|-----|------|------|
| k3s-server | 10.10.10.10 | 200 | Control-plane K3s |
| k3s-worker-1 | 10.10.10.11 | 201 | Worker K3s |
| k3s-worker-2 | 10.10.10.12 | 202 | Worker K3s |
| nfs-server | 10.10.10.13 | 203 | Serveur NFS (stockage persistant) |
| Passerelle | 10.10.10.1 | - | Bridge Proxmox (vmbr1) |

---

## Etape 3 : Generer une paire de cles SSH

Les cles SSH permettent un acces sans mot de passe aux VMs via cloud-init.

### 3.1 Generer les cles

```powershell
ssh-keygen -t ed25519 -C "mspr-cogip" -f $env:USERPROFILE\.ssh\id_mspr
```

Quand demande, laisser la passphrase vide (Entree) pour l'automatisation.

### 3.2 Recuperer la cle publique

```powershell
Get-Content $env:USERPROFILE\.ssh\id_mspr.pub
```

Copier le contenu affiche (commence par `ssh-ed25519 AAAA...`). Cette cle sera utilisee dans `terraform.tfvars`.

### 3.3 Fichiers generes

| Fichier | Role | A proteger |
|---------|------|------------|
| `~/.ssh/id_mspr` | Cle privee | NE JAMAIS partager |
| `~/.ssh/id_mspr.pub` | Cle publique | A copier dans tfvars |

---

## Etape 4 : Remplir les fichiers de configuration

### 4.1 Terraform (terraform.tfvars)

```powershell
cd C:\Users\PC-HUGO\MSPR\terraform
Copy-Item terraform.tfvars.example terraform.tfvars
notepad terraform.tfvars
```

Remplir avec les vraies valeurs :

```hcl
# --- Connexion Proxmox ---
proxmox_url      = "https://VOTRE_IP_PUBLIQUE:8006"
proxmox_user     = "root@pam"
proxmox_password = "<MOT_DE_PASSE_ROOT>"
proxmox_node     = "ns3139245"

# --- Template et stockage ---
template_name  = "ubuntu-k3s-template"
storage_pool   = "local"
network_bridge = "vmbr1"

# --- SSH ---
ssh_user       = "ubuntu"
ssh_public_key = "ssh-ed25519 AAAA... mspr-cogip"

# --- Reseau interne ---
gateway    = "10.10.10.1"
nameserver = "8.8.8.8"

ip_control_plane = "10.10.10.10/24"
ip_worker_1      = "10.10.10.11/24"
ip_worker_2      = "10.10.10.12/24"
ip_nfs           = "10.10.10.13/24"

# --- Application ---
ssh_private_key_path = "~/.ssh/id_mspr"
k3s_version          = "v1.29.2+k3s1"
odoo_domain          = "odoo.local"
nfs_export_path      = "/srv/nfs/k8s"
```

> **IMPORTANT** : `terraform.tfvars` est dans le `.gitignore` et ne sera JAMAIS commite dans Git. Ne pas partager ce fichier.

### 4.2 Ansible Vault (vault.yml)

```powershell
cd C:\Users\PC-HUGO\MSPR\ansible\group_vars\all
Copy-Item vault.yml.example vault.yml
notepad vault.yml
```

Contenu a remplir :

```yaml
vault_pg_password: "Ch4ng3M3!Pg2026"
vault_odoo_password: "admin"
```

> En production, chiffrer avec `ansible-vault encrypt vault.yml`. Pour le PoC, les valeurs en clair suffisent.

---

## Etape 5 : Creer le template VM

Le template est une image Ubuntu 22.04 LTS pre-configuree qui servira de base pour cloner les 4 VMs.

### 5.1 Executer le script sur Proxmox

```bash
ssh root@<IP-SERVEUR-OVH>

curl -fsSL https://raw.githubusercontent.com/VOTRE_ORGANISATION/mspr-cogip-k8s/main/setup/create-template.sh -o /root/create-template.sh
bash /root/create-template.sh
```

### 5.2 Ce que fait le script

1. Telecharge l'image cloud Ubuntu 22.04 (format qcow2, ~700 Mo)
2. Installe les paquets necessaires dans l'image via `virt-customize` :
   - `qemu-guest-agent`, `curl`, `wget`, `nfs-common`, `open-iscsi`, `jq`, `unzip`
3. Redimensionne le disque a 30 Go
4. Cree une VM (ID 9000) avec la configuration :
   - 2 CPU, 4 Go RAM, bridge `vmbr1`
   - Disque cloud-init pour l'injection SSH/reseau
5. Convertit la VM en template Proxmox

### 5.3 Verification

```bash
qm list | grep 9000
# Doit afficher : 9000  ubuntu-k3s-template  stopped
```

Le template est visible dans l'interface Proxmox sous l'icone de template (icone avec un petit engrenage).

### 5.4 Duree estimee

~3 minutes (selon la vitesse de telechargement et du stockage).

---

## Etape 6 : Lancer Terraform

Terraform va cloner le template 4 fois pour creer les VMs du cluster.

### 6.1 Initialiser et deployer

```powershell
cd C:\Users\PC-HUGO\MSPR\terraform

terraform init                                   # Telecharger le provider bpg/proxmox
terraform plan                                   # Previsualiser les 4 VMs
terraform apply -parallelism=1                   # Deployer (confirmer avec "yes")
```

> **Note** : Le `-parallelism=1` est recommande sur Proxmox pour eviter les conflits de verrous sur le stockage lors du clonage simultane.

### 6.2 Ce que fait Terraform

1. Clone le template 9000 en 4 VMs (IDs 200-203)
2. Configure chaque VM (CPU, RAM, disque, reseau via cloud-init)
3. Demarre les VMs automatiquement
4. Genere l'inventaire Ansible (`ansible/inventory/hosts.yml`)

### 6.3 Ressources creees

| VM | VMID | CPU | RAM | Disque | IP |
|----|------|-----|-----|--------|-----|
| k3s-server | 200 | 2 coeurs | 4 Go | 30 Go | 10.10.10.10 |
| k3s-worker-1 | 201 | 2 coeurs | 4 Go | 30 Go | 10.10.10.11 |
| k3s-worker-2 | 202 | 2 coeurs | 4 Go | 30 Go | 10.10.10.12 |
| nfs-server | 203 | 1 coeur | 1 Go | 50 Go | 10.10.10.13 |

### 6.4 Verification

```powershell
terraform output
# Affiche les IPs des 4 VMs
```

```bash
# Depuis Proxmox, verifier que les VMs sont demarrees
ssh root@<IP-SERVEUR-OVH> "qm list"
```

### 6.5 Duree estimee

~2-3 minutes.

---

## Etape 7 : Lancer Ansible

Ansible est execute **directement sur le serveur Proxmox** car les VMs sont sur le reseau interne (10.10.10.x), inaccessible depuis le PC local.

### 7.1 Preparer Ansible sur Proxmox

```bash
ssh root@<IP-SERVEUR-OVH>

# Installer Ansible et dependances
apt-get update -qq
apt-get install -y ansible python3-pip git
pip3 install --break-system-packages kubernetes PyYAML jsonpatch

# Cloner le depot
cd /root
git clone https://github.com/VOTRE_ORGANISATION/mspr-cogip-k8s.git
cd mspr-cogip-k8s/ansible

# Installer les collections Galaxy
ansible-galaxy collection install -r requirements.yml --force
```

### 7.2 Configurer l'acces SSH aux VMs

```bash
# Generer une cle SSH locale pour Ansible
ssh-keygen -t ed25519 -f /root/.ssh/id_ansible -N ''

# Injecter la cle dans les VMs via cloud-init
ANSIBLE_KEY=$(cat /root/.ssh/id_ansible.pub)
USER_KEY="ssh-ed25519 AAAA... mspr-cogip"   # Votre cle publique
TMPFILE=$(mktemp)
echo "$USER_KEY" > $TMPFILE
echo "$ANSIBLE_KEY" >> $TMPFILE

for vmid in 200 201 202 203; do
    qm set $vmid --sshkeys $TMPFILE
    qm cloudinit update $vmid
done
rm -f $TMPFILE

# Redemarrer les VMs pour appliquer cloud-init
for vmid in 200 201 202 203; do
    qm reboot $vmid
done

# Attendre ~90 secondes que les VMs rebootent
sleep 90
```

### 7.3 Creer l'inventaire Ansible

```bash
cd /root/mspr-cogip-k8s/ansible
mkdir -p inventory

cat > inventory/hosts.yml << 'EOF'
---
all:
  vars:
    ansible_user: ubuntu
    ansible_ssh_private_key_file: /root/.ssh/id_ansible
    ansible_python_interpreter: /usr/bin/python3
    k3s_version: "v1.29.2+k3s1"
    odoo_domain: "odoo.local"
  children:
    k3s_server:
      hosts:
        k3s-control-plane:
          ansible_host: 10.10.10.10
          k3s_role: server
    k3s_agents:
      hosts:
        k3s-worker-1:
          ansible_host: 10.10.10.11
          k3s_role: agent
        k3s-worker-2:
          ansible_host: 10.10.10.12
          k3s_role: agent
    nfs:
      hosts:
        nfs-server:
          ansible_host: 10.10.10.13
          nfs_export_path: /srv/nfs/k8s
    k3s_cluster:
      children:
        k3s_server:
        k3s_agents:
EOF

# Creer les symlinks pour les group_vars
ln -sf ../group_vars inventory/group_vars
ln -sf ../group_vars playbooks/group_vars
```

### 7.4 Preparer les VMs (fix dpkg + paquets Python)

Apres un clone cloud-init, dpkg peut etre dans un etat intermediaire. Il faut le corriger avant Ansible :

```bash
# Fix dpkg sur toutes les VMs
for ip in 10.10.10.10 10.10.10.11 10.10.10.12 10.10.10.13; do
    echo "--- $ip ---"
    ssh -o StrictHostKeyChecking=no -i /root/.ssh/id_ansible ubuntu@$ip \
        'sudo dpkg --configure -a && sudo apt --fix-broken install -y && sudo apt-get update -qq'
done

# Installer la librairie Python Kubernetes sur le control-plane
ssh -o StrictHostKeyChecking=no -i /root/.ssh/id_ansible ubuntu@10.10.10.10 \
    'sudo apt-get install -y python3-kubernetes python3-pip python3-yaml python3-jsonpatch'
```

### 7.5 Lancer le deploiement

```bash
cd /root/mspr-cogip-k8s/ansible

# Deploiement complet (K3s + NFS + Odoo)
ansible-playbook playbooks/site.yml -v
```

### 7.6 Ce que fait le playbook

Le playbook `site.yml` orchestre 5 roles dans l'ordre :

1. **common** : Mise a jour des paquets, configuration de base sur toutes les VMs
2. **nfs-server** : Installation et configuration du serveur NFS sur la VM dediee, export `/srv/nfs/k8s`
3. **k3s-server** : Installation de K3s en mode server sur le control-plane, recuperation du token
4. **k3s-agent** : Jointure des 2 workers au cluster via le token
5. **deploy-odoo** : Deploiement sur Kubernetes via le control-plane :
   - NFS Subdir External Provisioner (Helm) → StorageClass `nfs-client`
   - cert-manager (Helm, **optionnel**, desactive par defaut)
   - PostgreSQL 17 (manifest K8s natif, image officielle)
   - Odoo 18 (manifest K8s natif, image officielle)
   - Ingress Traefik HTTP (+ HTTPS si cert-manager active)

### 7.7 Initialiser la base Odoo

Apres le playbook, la base de donnees Odoo doit etre initialisee (premiere fois uniquement) :

```bash
ssh -i /root/.ssh/id_ansible ubuntu@10.10.10.10 bash << 'REMOTE'
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml

# Attendre que le pod Odoo soit Running
kubectl wait --for=condition=ready pod -l app=odoo -n odoo --timeout=120s

# Initialiser la DB avec les modules base et web
kubectl exec -n odoo deployment/odoo -- odoo -d odoo -i base,web --stop-after-init \
    --db_host=postgres --db_user=odoo --db_password='Ch4ng3M3!Pg2026' --without-demo=all

# Redemarrer Odoo pour prendre en compte l'init
kubectl rollout restart deployment/odoo -n odoo
REMOTE
```

### 7.8 Creer l'IngressRoute HTTP

K3s inclut Traefik comme Ingress Controller. Il faut creer une IngressRoute pour le trafic HTTP :

```bash
ssh -i /root/.ssh/id_ansible ubuntu@10.10.10.10 bash << 'REMOTE'
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml

cat > /tmp/odoo-http-route.yaml << 'YAML'
apiVersion: traefik.io/v1alpha1
kind: IngressRoute
metadata:
  name: odoo-http
  namespace: odoo
spec:
  entryPoints:
    - web
  routes:
    - match: Host(`odoo.local`)
      kind: Rule
      services:
        - name: odoo
          port: 8069
YAML

kubectl apply -f /tmp/odoo-http-route.yaml
REMOTE
```

### 7.9 Duree estimee

~10-15 minutes (K3s + NFS + deploiement Odoo + init DB).

---

## Etape 8 : Port-forwarding NAT + fichier hosts + acces Odoo

### 8.1 Configurer le port-forwarding sur Proxmox

```bash
ssh root@<IP-SERVEUR-OVH>

# Rediriger le port 80 (HTTP) vers le control-plane
iptables -t nat -A PREROUTING -i vmbr0 -p tcp --dport 80 -j DNAT --to-destination 10.10.10.10:80

# Rediriger le port 443 (HTTPS) vers le control-plane (pour plus tard si cert-manager active)
iptables -t nat -A PREROUTING -i vmbr0 -p tcp --dport 443 -j DNAT --to-destination 10.10.10.10:443

# Rendre les regles persistantes
apt-get install -y iptables-persistent
netfilter-persistent save
```

### 8.2 Modifier le fichier hosts sur le PC local

Ouvrir PowerShell **en administrateur** :

```powershell
Add-Content -Path "C:\Windows\System32\drivers\etc\hosts" -Value "`nVOTRE_IP_PUBLIQUE  odoo.local"
```

Verification :
```powershell
ping odoo.local
# Doit resoudre vers VOTRE_IP_PUBLIQUE
```

### 8.3 Acceder a Odoo

Ouvrir un navigateur et aller sur :
```
http://odoo.local
```

**Identifiants par defaut :**
| Champ | Valeur |
|-------|--------|
| Login | `admin` |
| Mot de passe | `admin` |

> Lors de la premiere connexion, Odoo peut afficher un selecteur de base de donnees. Selectionner la base `odoo`.

---

## Alternative : Deploiement automatique complet (MSPR)

Les scripts **`mspr-deploiement-complet.ps1`** (recommande sous Windows) et **`deploy-all.py`** automatisent **TOUTES** les etapes ci-dessus (sauf l'etape 0 et la configuration initiale du reseau Proxmox).

### Prerequis

- Etapes 0-2 deja effectuees (outils installes, reseau Proxmox configure)
- `terraform.tfvars` rempli

### Lancement

```powershell
cd <RACINE-DU-DEPOT>\setup
.\mspr-deploiement-complet.ps1
```

Equivalent : `python deploy-all.py` (meme repertoire `setup`).

**Reprise** apres echec Ansible (sans reset cluster / sans Terraform) :

```powershell
cd <RACINE-DU-DEPOT>\setup
.\mspr-reprise-ansible.ps1
```

(Option : definir avant `$env:MSPR_RESTART_VMS = "202"` pour forcer le reboot d'une VM Proxmox.)

### Ce que fait le script

| Etape | Action | Duree estimee |
|-------|--------|---------------|
| 1/7 | Reset cluster Proxmox (VMs 200-203) ; **template 9000 conserve** par defaut | ~15s |
| 2/7 | Template Packer **saute** si deja present sur Proxmox ; sinon build ISO | 0 a ~60min |
| 3/7 | Terraform apply (4 VMs + inventaire) | ~15-45min |
| 4/7 | Setup Ansible (install, clone, SSH keys, Galaxy) | ~3-45min |
| 5/7 | Playbook Ansible (K3s + NFS + Odoo) | ~5min |
| 6/7 | Init DB Odoo + IngressRoute + NAT | ~3min |
| 7/7 | Verification HTTP (health check) | ~1min |

### Fonctionnalites

- **Webhook Google Chat** : Notification a chaque etape (succes ou echec)
- **Chronometrage** : Temps de chaque etape + recapitulatif final
- **Retry automatique** : Terraform et SSH avec logique de retry en cas d'echec
- **Fix dpkg** : Correction automatique des problemes dpkg post-clone
- **Init Odoo** : Initialisation de la base de donnees avec les modules `base` + `web`

### Resultat

```
============================================================
RECAPITULATIF
============================================================
  Reset Proxmox            : 0m12s
  Template VM              : 2m30s
  Terraform                : 1m45s
  Setup Ansible            : 3m20s
  Ansible playbook         : 5m15s
  Init Odoo + NAT          : 2m40s
  Verification             : 0m45s
  ────────────────────────────────────────
  TOTAL                    : 16m27s
  Odoo: OK
============================================================
```

---

## Verification du cluster

### Depuis Proxmox (SSH vers le control-plane)

```bash
ssh -i /root/.ssh/id_ansible ubuntu@10.10.10.10
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml

# Verifier les noeuds du cluster
kubectl get nodes -o wide
# NAME            STATUS   ROLES                  AGE   VERSION
# k3s-server      Ready    control-plane,master   Xm    v1.29.2+k3s1
# k3s-worker-1    Ready    <none>                 Xm    v1.29.2+k3s1
# k3s-worker-2    Ready    <none>                 Xm    v1.29.2+k3s1

# Verifier tous les pods
kubectl get pods -A
# NAMESPACE     NAME                    READY   STATUS    RESTARTS   AGE
# kube-system   coredns-xxx             1/1     Running   0          Xm
# kube-system   traefik-xxx             1/1     Running   0          Xm
# storage       nfs-provisioner-xxx     1/1     Running   0          Xm
# odoo          postgres-xxx            1/1     Running   0          Xm
# odoo          odoo-xxx                1/1     Running   0          Xm

# Verifier l'Ingress
kubectl get ingress -n odoo
kubectl get ingressroute -n odoo

# Verifier le stockage
kubectl get pvc -n odoo
kubectl get sc
```

### Depuis le navigateur

- `http://odoo.local` → Interface web Odoo (login: admin / admin)

---

## Destruction de l'infrastructure

### Detruire uniquement les VMs (garder le template)

```powershell
cd C:\Users\PC-HUGO\MSPR\terraform
terraform destroy
```

### Detruire le cluster K8s uniquement (garder les VMs)

```bash
ssh root@<IP-SERVEUR-OVH>
cd /root/mspr-cogip-k8s/ansible
ansible-playbook playbooks/destroy.yml
```

### Reset complet (VMs + template + NAT)

Le script `deploy-all.py` fait un reset complet en etape 1 avant de tout recreer. Pour un reset manuel :

```bash
ssh root@<IP-SERVEUR-OVH>

for vmid in 200 201 202 203; do
    qm stop $vmid --timeout 15 2>/dev/null || true
    sleep 1
    qm destroy $vmid --purge 2>/dev/null || true
done
qm destroy 9000 --purge 2>/dev/null || true
iptables -t nat -F PREROUTING
```

---

## Depannage

### Les VMs n'ont pas acces a internet

```bash
# Verifier le NAT MASQUERADE
iptables -t nat -L POSTROUTING -v -n
# Doit contenir : MASQUERADE  all  --  10.10.10.0/24  0.0.0.0/0

# Verifier le forwarding
cat /proc/sys/net/ipv4/ip_forward
# Doit retourner 1

# Si manquant, relancer le script reseau
bash /root/configure-network.sh
```

### Terraform bloque sur "Error acquiring the state lock"

```bash
# Tuer les processus Terraform bloquants
taskkill /F /IM terraform.exe   # Sur Windows
# Supprimer le lock
del terraform\.terraform.lock.hcl
del terraform\terraform.tfstate
```

### Ansible : "dpkg was interrupted"

Les images cloud-init clonees peuvent avoir dpkg dans un etat instable :

```bash
ssh -i /root/.ssh/id_ansible ubuntu@10.10.10.10 \
    'sudo dpkg --configure -a && sudo apt --fix-broken install -y'
```

### Odoo affiche une erreur 500 ou "External ID not found"

La base de donnees n'est pas initialisee. Relancer l'init :

```bash
ssh -i /root/.ssh/id_ansible ubuntu@10.10.10.10 bash << 'REMOTE'
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
kubectl exec -n odoo deployment/postgres -- dropdb -U odoo odoo 2>/dev/null || true
kubectl exec -n odoo deployment/postgres -- createdb -U odoo -O odoo odoo
kubectl exec -n odoo deployment/odoo -- odoo -d odoo -i base,web --stop-after-init \
    --db_host=postgres --db_user=odoo --db_password='Ch4ng3M3!Pg2026' --without-demo=all
kubectl rollout restart deployment/odoo -n odoo
REMOTE
```

### Traefik retourne 404

L'IngressRoute HTTP n'est pas creee. Verifier et recreer :

```bash
ssh -i /root/.ssh/id_ansible ubuntu@10.10.10.10 \
    'export KUBECONFIG=/etc/rancher/k3s/k3s.yaml; kubectl get ingressroute -n odoo'
```

Si vide, recreer l'IngressRoute (voir etape 7.8).

### cert-manager echoue a demarrer

cert-manager est desactive par defaut car les images sont hebergees sur `quay.io` qui peut etre indisponible. Pour l'activer, ajouter dans `ansible/group_vars/all/vars.yml` :

```yaml
enable_cert_manager: true
```

---

## Resume des durees

| Etape | Action | Duree |
|-------|--------|-------|
| 0 | Installation outils (PC local) | ~10 min |
| 1 | Premier acces Proxmox | ~5 min |
| 2 | Configuration reseau NAT | ~5 min |
| 3 | Generation cles SSH | ~2 min |
| 4 | Configuration tfvars + vault | ~5 min |
| 5 | Creation template VM | ~3 min |
| 6 | Terraform apply | ~3 min |
| 7 | Ansible + init Odoo | ~10 min |
| 8 | Port-forwarding + test | ~2 min |
| **Total** | **Premiere mise en place complete** | **~45 min** |
| **PRA** | **Reconstruction depuis zero (deploy-all.py)** | **~20 min** |

---

## Architecture deployee

```
Internet
    |
    v
+------------------------------------------------------------+
|  Proxmox VE (IP publique)                                  |
|  vmbr0 (public) --- NAT iptables --- vmbr1 (10.10.10.1)   |
|                                                            |
|  NAT PREROUTING :80  -> 10.10.10.10:80  (Traefik HTTP)    |
|  NAT PREROUTING :443 -> 10.10.10.10:443 (Traefik HTTPS)   |
|                                                            |
|  +------------------------------------------------------+  |
|  | k3s-server (10.10.10.10) -- 2 CPU / 4 Go / 30 Go    |  |
|  |   Traefik (Ingress Controller)                       |  |
|  |   CoreDNS, ServiceLB, Metrics Server                 |  |
|  |   PostgreSQL 17 (pod, namespace odoo)                |  |
|  +------------------------------------------------------+  |
|  | k3s-worker-1 (10.10.10.11) -- 2 CPU / 4 Go / 30 Go  |  |
|  |   Odoo 18 (pod, namespace odoo)                      |  |
|  |   NFS Provisioner (pod, namespace storage)           |  |
|  +------------------------------------------------------+  |
|  | k3s-worker-2 (10.10.10.12) -- 2 CPU / 4 Go / 30 Go  |  |
|  |   (reserve pour scaling)                             |  |
|  +------------------------------------------------------+  |
|  | nfs-server (10.10.10.13) -- 1 CPU / 1 Go / 50 Go    |  |
|  |   /srv/nfs/k8s (Persistent Volumes)                  |  |
|  +------------------------------------------------------+  |
+------------------------------------------------------------+
```
