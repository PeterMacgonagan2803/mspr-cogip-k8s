# Architecture globale de la solution

## 1. Vue d'ensemble

La solution proposee a la COGIP repose sur une architecture bare-metal virtualisee via Proxmox VE (serveur dedie OVH), hebergeant un cluster Kubernetes K3s de 3 noeuds, avec un serveur NFS dedie au stockage persistant. Le reseau interne utilise un bridge NAT (`vmbr1`) avec port-forwarding vers l'exterieur.

**Acces applicatif** : par defaut, l'utilisateur accede a Odoo en **HTTP** sur `http://odoo.local` (resolution DNS locale vers l'IP publique du serveur, ports 80 forwards vers Traefik). Le deploiement de **cert-manager** et le routage **HTTPS** sont **optionnels** (variable `enable_cert_manager`, desactivee par defaut dans le projet), a activer lorsque les registres d'images et l'emission de certificats sont stables.

**Plan de reprise d'activite (PRA)** : l'infrastructure est entierement reproductible via le template Proxmox, Terraform et Ansible ; le temps de reconstruction de zero jusqu'a une interface Odoo utilisable est estime a **environ 20 minutes** (voir section 7).

## 2. Schema d'architecture reseau

```
                    +---------------------+
                    |   Utilisateur        |
                    |   http://odoo.local  |
                    +----------+----------+
                               |
                               | HTTP (port 80) par defaut
                               | HTTPS (443) si cert-manager active
                               v
+--------------------------------------------------------------+
|              Serveur Dedie OVH (Proxmox VE)                  |
|              IP publique : x.x.x.x                           |
|                                                              |
|  iptables NAT (PREROUTING)                                   |
|  :80  --> 10.10.10.10:80  (Traefik HTTP / web)               |
|  :443 --> 10.10.10.10:443 (Traefik HTTPS si TLS configure)   |
|                                                              |
|  +--------------------------------------------------------+  |
|  |           Reseau prive vmbr1 (10.10.10.0/24)           |  |
|  +--+-------------+-------------+-------------+-----------+  |
|     |             |             |             |               |
|     v             v             v             v               |
|  +------+    +------+    +------+    +----------+             |
|  | CP   |    | W1   |    | W2   |    | NFS      |             |
|  |.10.10|    |.10.11|    |.10.12|    |.10.13    |             |
|  |2C/4G |    |2C/4G |    |2C/4G |    |1C/1G    |             |
|  |30 Go |    |30 Go |    |30 Go |    |50 Go    |             |
|  +--+---+    +--+---+    +--+---+    +----+-----+             |
|     |          |          |               |                   |
|     +-----+----+----------+               |                   |
|           | K3s Cluster                   |                   |
|           |                               |                   |
|           |  +-------------------------+  |                   |
|           |  | kube-system             |  |                   |
|           |  |  +- CoreDNS             |  |                   |
|           |  |  +- Traefik (Ingress) <-+- HTTP (defaut)        |
|           |  |  +- ServiceLB           |  |                   |
|           |  |  +- Metrics Server      |  |                   |
|           |  +-------------------------+  |                   |
|           |  | storage                 |  |                   |
|           |  |  +- NFS Provisioner ----+--->  NFS mount       |
|           |  +-------------------------+                      |
|           |  | cert-manager (OPTIONNEL)|                      |
|           |  |  si enable_cert_manager|                      |
|           |  |  +- ClusterIssuer      |                      |
|           |  |    (selfsigned)         |                      |
|           |  +-------------------------+                      |
|           |  | odoo                    |                      |
|           |  |  +- PostgreSQL (pod)    |                      |
|           |  |    image postgres:17   |                      |
|           |  |  +- Odoo (pod)          |                      |
|           |  |    image odoo:18        |                      |
|           |  |  +- PVC --> NFS PV      |                      |
|           |  +-------------------------+                      |
|           |                                                   |
+--------------------------------------------------------------+
```

Les disques des trois noeuds K3s (control-plane et workers) sont dimensionnes a **30 Go** chacun pour accueillir les images de conteneurs, les donnees etcd et la marge d'evolution du PoC. La VM **NFS** dispose de **50 Go** pour les volumes persistants PostgreSQL et Odoo et les sous-repertoires crees par le provisioner dynamique.

## 3. Flux reseau detaille

### Acces utilisateur a Odoo

```
Utilisateur --> DNS local (odoo.local -> IP publique OVH)
            --> iptables NAT sur Proxmox (port 80 en configuration standard)
            --> Traefik sur K3s (Ingress Controller, entrypoint web)
            --> Service ClusterIP odoo (port 8069)
            --> Pod Odoo
            --> Pod PostgreSQL (connexion interne port 5432)
            --> PVC -> NFS PV -> VM NFS (/srv/nfs/k8s)
```

Lorsque **cert-manager** est active et qu'un certificat est associe a l'Ingress, le meme chemin peut etre expose en **HTTPS** sur le port 443 via l'entrypoint `websecure` de Traefik ; ce n'est pas le chemin par defaut du depot.

### Communication inter-noeuds

| Source | Destination | Port | Protocole |
|--------|-------------|------|-----------|
| Exterieur -> Proxmox | iptables NAT | 80 (defaut), 443 (optionnel TLS) | TCP |
| Proxmox NAT -> Control-plane | Traefik | 80, 443 | TCP |
| Workers -> Control-plane | API Server | 6443 | HTTPS |
| Control-plane -> Workers | Kubelet | 10250 | HTTPS |
| Tous les noeuds | CoreDNS | 53 | UDP/TCP |
| Tous les noeuds | NFS Server | 2049 | TCP |

## 4. Composants Kubernetes deployes

| Namespace | Composant | Type | Role |
|-----------|-----------|------|------|
| `kube-system` | CoreDNS | Deployment | Resolution DNS intra-cluster |
| `kube-system` | Traefik | Deployment | Ingress Controller ; HTTP par defaut, TLS si cert-manager |
| `kube-system` | ServiceLB | DaemonSet | LoadBalancer L4 |
| `kube-system` | Metrics Server | Deployment | Metriques CPU/RAM |
| `storage` | NFS Provisioner | Deployment | StorageClass dynamique (Helm nfs-subdir-external-provisioner) |
| `cert-manager` | cert-manager | Deployment | **OPTIONNEL** -- deploye uniquement si `enable_cert_manager=true` |
| `cert-manager` | ClusterIssuer | CR | Emetteur autosigne (PoC) -- present seulement avec cert-manager |
| `odoo` | PostgreSQL | Deployment | Base de donnees, image officielle **postgres:17** |
| `odoo` | Odoo | Deployment | Application ERP, image officielle **odoo:18** |
| `odoo` | Ingress | Ingress | Route **HTTP** vers Odoo par defaut ; HTTPS si TLS configure |

Les workloads **Odoo** et **PostgreSQL** sont deployes via **manifests Kubernetes natifs** (Deployments, Services, PVC, Ingress), et non via le chart Helm Bitnami, afin de matriser les versions d'images et d'eviter la dependance a des tags de chart obsoletes.

## 5. Stockage

```
Pod Odoo --> PVC (5Gi) --> PV --> NFS Server (/srv/nfs/k8s/odoo-data-...)
Pod PG   --> PVC (5Gi) --> PV --> NFS Server (/srv/nfs/k8s/pg-data-...)
```

Le `StorageClass` `nfs-client` (deploye via nfs-subdir-external-provisioner) cree automatiquement un sous-repertoire sur le serveur NFS pour chaque PVC demande.

**Politique de retention** : `Retain` -- les donnees sont conservees meme si le PVC est supprime, garantissant la protection des donnees de la COGIP.

## 6. Haute disponibilite et resilience

| Composant | Resilience |
|-----------|------------|
| **Pods Odoo** | Kubernetes redemarre automatiquement les pods en cas de crash |
| **Workers** | Si un worker tombe, les pods sont replanifies sur l'autre worker |
| **Stockage** | NFS externalise, independant des workers ; disque VM 50 Go pour le PoC |
| **Control-plane** | Point unique (1 seul), acceptable pour un PoC |
| **PRA** | Infrastructure entierement reproductible via IaC en **environ 20 minutes** (template, Terraform, Ansible, initialisation Odoo) |

> En production, il faudrait 3 control-planes et une solution de stockage repliquee (Longhorn, etc.).

## 7. Chaine d'automatisation complete

Les etapes suivantes decrivent l'ordre logique de reconstruction ; les durees sont indicatives, mesurees sur un deploiement type depuis une machine d'orchestration adaptee (par exemple execution Ansible depuis le serveur Proxmox).

```
 Etape 1       Etape 2         Etape 3           Etape 4            Etape 5
+--------+  +-----------+  +--------------+  +----------------+  +-------------+
|Template|  | Terraform |  | Ansible K3s  |  | Ansible Odoo   |  | Init Odoo   |
| ~1 min |->| ~2 min    |->| ~3 min       |->| ~5 min         |->| ~5 min      |
|        |  |           |  |              |  |                |  |             |
|Cloud-  |  |4 VMs      |  |Cluster 3     |  |NFS Provisioner |  |Base + admin |
|init    |  |30/50 Go   |  |noeuds        |  |Manifests PG/   |  |via script   |
|template|  |Inventaire |  |              |  |Odoo, Ingress   |  |Python       |
|VM 9000 |  |Ansible    |  |              |  |cert-manager si |  |(optionnel   |
|        |  |           |  |              |  |variable true   |  |si necessaire)|
+--------+  +-----------+  +--------------+  +----------------+  +-------------+

Temps total de reconstruction (zero -> Odoo accessible en HTTP) : ~20 minutes
```

Le script **`setup/deploy-all.py`** (lorsqu'il est utilise) enchaine ces phases avec des notifications par **webhook** (succes ou echec), ce qui automatise le deploiement complet et facilite l'integration dans une chaine d'integration ou la supervision humaine.

**Synthese des durees** : creation / clone du template (~1 min), `terraform apply` pour les quatre VMs (~2 min), playbooks Ansible cluster K3s (~3 min), role deploiement Odoo (NFS, manifests applicatifs, Ingress HTTP ; cert-manager conditionnel) (~5 min), initialisation de la base et premier acces (~5 min). Les variations dependent du reseau, du cache d'images sur les noeuds et de la disponibilite des registres (Docker Hub, quay.io pour cert-manager si active).
