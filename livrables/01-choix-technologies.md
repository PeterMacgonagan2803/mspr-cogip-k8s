# Mission 1 : Choix des technologies et justification

## 1. Contexte

La societe COGIP a besoin d'une infrastructure evolutive, performante et resiliente pour heberger son ERP Odoo a destination de son client Tesker. L'infrastructure doit etre entierement reproductible via de l'Infrastructure as Code (IaC) afin de garantir un Plan de Reprise d'Activite (PRA) fiable.

## 2. Distribution Kubernetes : K3s

### Choix retenu : **K3s** (par Suse/Rancher)

### Justification

| Critere | K3s | RKE2 | K0s | MicroK8s |
|---------|-----|------|-----|----------|
| **Legerete** | Single binary ~50Mo | Plus lourd | Leger | Snap-based |
| **LoadBalancer integre** | Oui (ServiceLB) | Non (Calico) | Non (MetalLB requis) | Partiel |
| **Ingress integre** | Oui (Traefik) | Non | Non | Partiel |
| **Facilite d'installation** | 1 commande curl | Moyenne | Moyenne | snap install |
| **Consommation RAM** | ~512 Mo | ~1 Go | ~512 Mo | ~800 Mo |
| **Production-ready** | Oui (certifie CNCF) | Oui | Oui | Oui |
| **Documentation** | Excellente | Bonne | Bonne | Bonne |

**Pourquoi K3s et pas les autres :**

- **LoadBalancer + Ingress integres** : K3s embarque nativement ServiceLB et Traefik, ce qui reduit significativement le nombre de composants a deployer et maintenir, contrairement a K0s ou RKE2 qui necessitent MetalLB et ingress-nginx separement.
- **Legerete** : Un seul binaire de ~50 Mo, ideal pour un PoC avec des VMs aux ressources limitees (2 CPU / 4 Go RAM).
- **Certification CNCF** : K3s est une distribution Kubernetes certifiee conforme, garantissant la compatibilite avec l'ecosysteme Kubernetes standard.
- **Rapidite de deploiement** : Installation en une seule commande, reduisant le risque d'erreurs lors du provisionnement Ansible.

### Pourquoi pas une solution cloud managee (GKE, AKS, EKS) ?

- Cout mensuel non negligeable (~40-50EUR/mois minimum).
- Dependance a un fournisseur cloud (vendor lock-in).
- Le bare-metal via Proxmox permet un controle total de l'infrastructure et une meilleure comprehension des composants sous-jacents, plus pertinent dans un contexte de PoC et d'apprentissage.

## 3. Hyperviseur : Proxmox VE

### Justification

- **Open-source** et gratuit (licence communautaire).
- **API REST complete** permettant l'automatisation via Terraform (provider `bpg/proxmox`).
- **Support de cloud-init** pour l'initialisation automatique des VMs.
- **KVM/QEMU** comme hyperviseur sous-jacent, offrant des performances proches du bare-metal.
- Largement utilise dans les environnements de laboratoire et de formation.

## 4. Outils d'Infrastructure as Code

### Packer / Cloud-init -- Creation de templates VM

| Aspect | Detail |
|--------|--------|
| **Role** | Creer un template de VM Ubuntu 22.04 LTS pre-configure |
| **Methode** | Image cloud Ubuntu (qcow2) + configuration cloud-init |
| **Pourquoi** | Garantir une base identique et reproductible pour toutes les VMs |
| **Ce qu'il installe** | qemu-guest-agent, curl, nfs-common, open-iscsi, ca-certificates |
| **Avantage PRA** | Recreation rapide des VMs a partir d'un template standardise |

### Terraform -- Provisionnement de l'infrastructure

| Aspect | Detail |
|--------|--------|
| **Role** | Deployer les 4 VMs sur Proxmox (clone du template cloud-init) |
| **Provider** | `bpg/proxmox` (>= 0.38.0) |
| **Pourquoi Terraform** | Declaratif, idempotent, gestion d'etat (tfstate), plan avant apply |
| **Avantage PRA** | `terraform apply` recree l'infrastructure identique en quelques minutes |
| **Bonus** | Generation automatique de l'inventaire Ansible |

### Ansible -- Configuration et deploiement applicatif

| Aspect | Detail |
|--------|--------|
| **Role** | Configurer les VMs, deployer K3s, installer Odoo via manifests K8s |
| **Pourquoi Ansible** | Agentless (SSH), declaratif, idempotent, large ecosysteme Galaxy |
| **Collections utilisees** | `kubernetes.core` (Helm, K8s), `ansible.posix`, `community.general` |
| **Avantage PRA** | `ansible-playbook site.yml` recree le cluster et l'applicatif complet |

## 5. Stockage persistant : NFS + nfs-subdir-external-provisioner

- Solution la plus legere pour du stockage distant sous Kubernetes en bare-metal.
- Une VM NFS dediee avec **disque 50 Go** fournit les volumes persistants via un `StorageClass` automatique (les noeuds K3s utilisent des disques **30 Go** chacun pour le systeme et les donnees locales du cluster).
- Alternatives plus lourdes (Longhorn, OpenEBS) ecartees car trop gourmandes en ressources pour un PoC.

## 6. Certificats TLS : cert-manager (optionnel)

- **cert-manager n'est plus une dependance obligatoire** du deploiement : il est **parametrable** via la variable Ansible `enable_cert_manager`, qui **vaut `false` par defaut**.
- **Motif du defaut desactive (PoC)** : le chart cert-manager et ses images s'appuient notamment sur le registre **quay.io**, qui a connu des indisponibilites pendant la realisation du projet ; desactiver cert-manager par defaut garantit un deploiement reproductible sans bloquer sur une image externe.
- **Lorsque `enable_cert_manager: true`** : le role deploie cert-manager (Helm Jetstack), cree un `ClusterIssuer` autosigne, et l'Ingress expose alors le TLS (certificats autosignes adaptes au laboratoire). En production, le meme mecanisme permettrait de basculer vers Let's Encrypt en adaptant l'issuer.
- **Acces applicatif sans cert-manager** : Odoo reste pleinement utilisable en **HTTP** (par exemple `http://odoo.local`) pour le PoC et les demonstrations ; le cahier des charges fonctionnel est respecte sans TLS obligatoire.

## 7. Synthese de la chaine d'automatisation

```
Image cloud Ubuntu 22.04
     |
     v
  [Cloud-init / Script]  -->  Template VM Proxmox (ID 9000)
                                   |
                                   v
                            [Terraform]  -->  4 VMs : CP + 2 Workers (30 Go/disque)
                                                 + NFS (50 Go/disque)
                                                 + inventaire Ansible auto-genere
                                                 v
                                           [Ansible]  -->  K3s Cluster
                                                            |
                                                            v
                                                      [Ansible + Helm/K8s]  -->  NFS Provisioner
                                                                                  [cert-manager] (optionnel)
                                                                                  Odoo + PostgreSQL (manifests K8s, images officielles)
                                                                                  Ingress : HTTP par defaut ; HTTP+HTTPS si cert-manager active
```

**Chaines obligatoires vs optionnelles :** Terraform, Ansible, K3s, NFS provisioner, PostgreSQL, Odoo et Ingress **HTTP** forment le socle minimal. **cert-manager** et le bloc **TLS** de l'Ingress sont **optionnels** (desactives par defaut).

**Temps de reconstruction complete (PRA) estime : ~20 minutes** depuis zero (template + `terraform apply` + playbooks Ansible jusqu'a Odoo joignable en HTTP), avec une commande principale par grande etape (Terraform puis Ansible), selon la charge du stockage Proxmox et le reseau.
