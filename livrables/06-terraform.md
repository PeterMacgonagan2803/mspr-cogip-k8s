# Mission 5 : Terraform -- Preparation et deploiement de l'infrastructure

## 1. Objectif

Deployer automatiquement les 4 machines virtuelles necessaires au cluster K3s sur Proxmox, a partir du template cloud-init, et generer l'inventaire Ansible correspondant.

## 2. Structure des fichiers

```
terraform/
  providers.tf              # Configuration du provider bpg/proxmox
  variables.tf              # Definition de toutes les variables
  main.tf                   # Ressources principales (VMs)
  inventory.tf              # Generation automatique de l'inventaire Ansible
  outputs.tf                # Sorties (IPs, infos VMs)
  terraform.tfvars.example  # Exemple de configuration (a copier/adapter)
  templates/
    hosts.yml.tftpl         # Template pour l'inventaire Ansible
```

## 3. Provider Proxmox

Le provider **`bpg/proxmox`** (version >= 0.38.0) permet a Terraform de communiquer avec l'API Proxmox pour creer, modifier et supprimer des VMs. Ce provider a ete choisi plutot que `telmate/proxmox` pour sa meilleure compatibilite avec les permissions Proxmox et son support SSH natif.

```hcl
provider "proxmox" {
  endpoint = var.proxmox_url
  username = var.proxmox_user
  password = var.proxmox_password
  insecure = true

  ssh {
    agent    = false
    username = "root"
    password = var.proxmox_password
  }
}
```

L'authentification se fait via **utilisateur/mot de passe** Proxmox :
1. L'endpoint pointe vers l'API Proxmox (port 8006)
2. Le bloc `ssh` permet a Terraform de gerer les operations necessitant un acces direct au noeud

## 4. Ressources deployees

### VMs provisionnees via `for_each`

Terraform utilise une boucle `for_each` sur une map `locals` pour deployer les 4 VMs en une seule ressource :

| VM | VMID | CPU | RAM | Disque | Role |
|----|------|-----|-----|--------|------|
| `k3s-server` | 200 | 2 coeurs | 4 Go | 30 Go | Control-plane K3s |
| `k3s-worker-1` | 201 | 2 coeurs | 4 Go | 30 Go | Worker K3s |
| `k3s-worker-2` | 202 | 2 coeurs | 4 Go | 30 Go | Worker K3s |
| `nfs-server` | 203 | 1 coeur | 1 Go | 50 Go | Serveur NFS |

### Configuration reseau

Chaque VM recoit via cloud-init :
- Une **IP statique** configuree via le bloc `initialization`
- Un acces au **gateway** reseau (NAT sur Proxmox)
- Un serveur **DNS** (configurable, par defaut `8.8.8.8`)
- Une **cle SSH publique** pour l'acces sans mot de passe

### Clone du template

```hcl
clone {
  vm_id = 9000    # Template cree par le script create-template.sh
  full  = true    # Clone complet (pas un linked clone)
}
```

## 5. Generation automatique de l'inventaire Ansible

L'un des points forts de notre infrastructure : Terraform genere automatiquement le fichier `ansible/inventory/hosts.yml` apres le deploiement des VMs. Plus besoin de copier manuellement les IPs.

Le fichier `inventory.tf` utilise `templatefile()` pour remplir le template `hosts.yml.tftpl` avec les IPs reelles des VMs deployees.

**Avantage** : Un seul `terraform apply` cree les VMs ET prepare l'inventaire Ansible. Zero intervention manuelle entre les deux etapes.

## 6. Outputs

Apres `terraform apply`, les sorties affichent :

```
control_plane_ip = "10.10.10.10"
worker_1_ip      = "10.10.10.11"
worker_2_ip      = "10.10.10.12"
nfs_server_ip    = "10.10.10.13"
```

## 7. Variables parametrables

| Variable | Description | Defaut |
|----------|-------------|--------|
| `proxmox_url` | URL API Proxmox | (requis) |
| `proxmox_user` | Utilisateur Proxmox | `root@pam` |
| `proxmox_password` | Mot de passe Proxmox | (requis, sensible) |
| `proxmox_node` | Noeud Proxmox cible | (requis) |
| `template_name` | Nom du template | `ubuntu-k3s-template` |
| `storage_pool` | Pool de stockage | `local-lvm` |
| `ip_control_plane` | IP du control-plane (CIDR) | (requis) |
| `ip_worker_1` | IP du worker 1 (CIDR) | (requis) |
| `ip_worker_2` | IP du worker 2 (CIDR) | (requis) |
| `ip_nfs` | IP du serveur NFS (CIDR) | (requis) |
| `gateway` | Passerelle reseau | (requis) |
| `k3s_version` | Version K3s | `v1.29.2+k3s1` |
| `odoo_domain` | Domaine Odoo | `odoo.local` |

## 8. Commandes d'utilisation

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars  # Copier et adapter
terraform init                                 # Initialiser les providers
terraform plan                                 # Previsualiser les changements
terraform apply                                # Deployer l'infrastructure
terraform destroy                              # Supprimer l'infrastructure
```

## 9. Gestion de l'etat (tfstate)

Le fichier `terraform.tfstate` contient l'etat de l'infrastructure deployee. Il est exclu du depot Git (`.gitignore`) car il peut contenir des informations sensibles. En production, il serait stocke dans un backend distant (S3, Consul, etc.).

## 10. Interet pour le PRA

`terraform apply` recree l'ensemble des 4 VMs en **environ 10 a 15 minutes** en pratique (clone complet depuis le template, allocation disque 30/30/30/50 Go, demarrage cloud-init), la duree exacte dependant surtout du **type de stockage Proxmox** (SSD vs disque mecanique) et de la charge du cluster.

Le **PRA complet depuis zero** (infrastructure Terraform + configuration Ansible + deploiement Odoo sur K3s) est estime a **environ 20 minutes** lorsque les prerequis (template, secrets Vault) sont deja en place. Combine avec le template cloud-init, aucune saisie manuelle des adresses IP n'est necessaire entre Terraform et Ansible : l'inventaire est regenere automatiquement.
