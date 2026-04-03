# MSPR TPRE961 — Infrastructure COGIP / Tesker (K3s + Odoo)

Projet de **mise en situation professionnelle reconstituée** (EISI) : PoC d’infrastructure pour la société fictive **COGIP**, hébergeant **Odoo** sur un cluster **Kubernetes** (distribution **K3s**), avec **Packer**, **Terraform** (Proxmox) et **Ansible** (dont `kubernetes.core.helm`), conformément au cahier des charges **TPRE961 (Infra)**.

## Architecture cible

- **1 control-plane** + **2 workers** K3s, **1 VM NFS** (stockage persistant, `nfs-subdir-external-provisioner`).
- **Odoo** déployé via le chart Helm **Bitnami** ; accès **HTTPS** avec **certificat TLS autosigné** (Traefik intégré à K3s).
- **Infrastructure as Code** : recettes versionnées (pas de secrets dans le dépôt public).

## Prérequis

- Terraform ≥ 1.5, Packer, Ansible ≥ 2.15, Helm 3.
- Serveur **Proxmox VE** (ou adapter le provider Terraform pour un autre cloud / lab).
- Fichier `terraform/terraform.tfvars` (copié depuis `terraform.tfvars.example`) — **ne jamais le committer**.

## Déploiement (résumé)

1. **Packer** : construire le template Ubuntu (répertoire `packer/`).
2. **Terraform** : `terraform init && terraform apply` dans `terraform/` → génère `ansible/inventory/hosts.yml`.
3. **Ansible** (depuis une machine qui joint les VMs, souvent le Proxmox) :

```bash
cd ansible
ansible-galaxy collection install -r requirements.yml
# Optionnel : cp group_vars/all/vault.yml.example group_vars/all/vault.yml puis ansible-vault encrypt
ansible-playbook playbooks/site.yml
```

4. Accès : `https://odoo.local` (ajouter la résolution DNS ou une entrée `hosts` vers l’IP exposée — souvent IP publique avec **NAT** 443 vers le control-plane, voir `setup/GUIDE-DEMARRAGE.md`).

## Déploiement automatisé depuis Windows (`deploy-all.py`)

Variables d’environnement **obligatoires** avant `python deploy-all.py` :

| Variable | Rôle |
|----------|------|
| `MSPR_PROXMOX_HOST` | IP ou FQDN du Proxmox |
| `MSPR_PROXMOX_PASS` | Mot de passe root Proxmox |
| `MSPR_GIT_URL` | URL **git** de **ce** dépôt (clone sur le serveur pour Packer / Ansible) |

Optionnel : `MSPR_PROXMOX_NODE` (défaut `pve`), `MSPR_WEBHOOK_URL`, `MSPR_GIT_URL` branche via `-b main` dans les scripts shell générés.

Lanceur PowerShell : `setup/mspr-deploiement-complet.ps1`.

## Structure du dépôt

```
terraform/     # VMs Proxmox + génération inventaire Ansible
ansible/       # K3s, NFS, déploiement Helm (NFS + Bitnami Odoo)
packer/        # Template cloud-init Ubuntu 22.04
setup/         # Guides et orchestration (deploy-all.py)
livrables/     # Documentation par mission (Gantt, Kanban, etc.)
```

## Livrables pédagogiques

Les missions 1 à 8 du sujet sont documentées sous `livrables/` (choix techno, Gantt, Kanban, inclusivité, Packer, Terraform, Ansible, architecture, dossier de rendu).

## CI

Le workflow GitHub Actions valide Terraform, Packer et `ansible-lint` sur les playbooks et rôles.

## Sécurité

- Aucun mot de passe Proxmox ou webhook dans le code : utiliser **uniquement** des variables d’environnement ou `terraform.tfvars` / **Ansible Vault** (`vault.yml` est ignoré par Git ; voir `vault.yml.example`).
