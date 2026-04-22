# Architecture globale de la solution

## 1. Vue d'ensemble

La solution proposee a la COGIP repose sur une architecture bare-metal virtualisee via Proxmox VE (serveur dedie OVH), hebergeant un cluster Kubernetes K3s de 3 noeuds, avec un serveur NFS dedie au stockage persistant. Le reseau interne utilise un bridge NAT (`vmbr1`) avec port-forwarding vers l'exterieur.

**Acces applicatif** : l'utilisateur accede a Odoo en **HTTPS** sur `https://odoo.local` (certificat **autosigne** fourni par le chart Bitnami ; accepter l'avertissement du navigateur). Le NAT Proxmox redirige en general les ports **443** (et souvent 80) vers le control-plane ou le service expose par Traefik.

**Plan de reprise d'activite (PRA)** : l'infrastructure est entierement reproductible via le template Proxmox, Terraform et Ansible ; le temps de reconstruction de zero jusqu'a une interface Odoo utilisable est estime a **environ 20 minutes** (voir section 7).

## 2. Schema d'architecture reseau

```
                    +---------------------+
                    |   Utilisateur        |
                    | https://odoo.local   |
                    +----------+----------+
                               |
                               | HTTPS (443) — TLS autosigne (chart Bitnami)
                               | HTTP (80) possible selon NAT / tests
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
|  |2C/4G |    |2C/4G |    |2C/4G |    |2C/2G    |             |
|  |30 Go |    |30 Go |    |30 Go |    |50 Go    |             |
|  +--+---+    +--+---+    +--+---+    +----+-----+             |
|     |          |          |               |                   |
|     +-----+----+----------+               |                   |
|           | K3s Cluster                   |                   |
|           |                               |                   |
|           |  +-------------------------+  |                   |
|           |  | kube-system             |  |                   |
|           |  |  +- CoreDNS             |  |                   |
|           |  |  +- Traefik (Ingress) <-+- HTTP web + HTTPS websecure (PoC) |
|           |  |  +- ServiceLB           |  |                   |
|           |  |  +- Metrics Server      |  |                   |
|           |  +-------------------------+  |                   |
|           |  | storage                 |  |                   |
|           |  |  +- NFS Provisioner ----+--->  NFS mount       |
|           |  +-------------------------+                      |
|           |  | odoo (Helm Bitnami)     |                      |
|           |  |  +- PostgreSQL (subchart)|                      |
|           |  |  +- Odoo workload      |                      |
|           |  |  +- PVC --> NFS PV      |                      |
|           |  +-------------------------+                      |
|           |                                                   |
+--------------------------------------------------------------+
```

Les disques des trois noeuds K3s (control-plane et workers) sont dimensionnes a **30 Go** chacun pour accueillir les images de conteneurs, les donnees etcd et la marge d'evolution du PoC. La VM **NFS** dispose de **50 Go** pour les volumes persistants PostgreSQL et Odoo et les sous-repertoires crees par le provisioner dynamique.

## 3. Flux reseau detaille

### Acces utilisateur a Odoo

```
Utilisateur --> DNS local (odoo.local -> IP publique)
            --> iptables NAT Proxmox (souvent 443 -> Traefik)
            --> Traefik (entrypoints **web** + **websecure**, TLS secret Helm)
            --> Service Odoo (chart Bitnami)
            --> Pods Odoo / PostgreSQL
            --> PVC -> NFS PV -> VM NFS (/srv/nfs/k8s)
```

### Communication inter-noeuds

| Source | Destination | Port | Protocole |
|--------|-------------|------|-----------|
| Exterieur -> Proxmox | iptables NAT | 80, 443 (HTTPS PoC) | TCP |
| Proxmox NAT -> Control-plane | Traefik | 80, 443 | TCP |
| Workers -> Control-plane | API Server | 6443 | HTTPS |
| Control-plane -> Workers | Kubelet | 10250 | HTTPS |
| Tous les noeuds | CoreDNS | 53 | UDP/TCP |
| Tous les noeuds | NFS Server | 2049 | TCP |

## 4. Composants Kubernetes deployes

| Namespace | Composant | Type | Role |
|-----------|-----------|------|------|
| `kube-system` | CoreDNS | Deployment | Resolution DNS intra-cluster |
| `kube-system` | Traefik | Deployment | Ingress Controller (HTTP + HTTPS / websecure) |
| `kube-system` | ServiceLB | DaemonSet | LoadBalancer L4 |
| `kube-system` | Metrics Server | Deployment | Metriques CPU/RAM |
| `storage` | NFS Provisioner | Deployment | StorageClass dynamique (Helm nfs-subdir-external-provisioner) |
| `odoo` | Release Helm `odoo` | Helm | Chart Bitnami (Odoo + PostgreSQL, persistance NFS) |
| `odoo` | Ingress | Ingress | **HTTPS** TLS autosigne (valeurs chart) |

Les workloads applicatifs sont deployes via le **chart Helm Bitnami Odoo** (`kubernetes.core.helm`), avec persistance sur la **StorageClass NFS**.

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
|VM 9000 |  |Ansible    |  |              |  |Helm Odoo Bitnami|  |HTTPS PoC    |
|        |  |           |  |              |  |variable true   |  |si necessaire)|
+--------+  +-----------+  +--------------+  +----------------+  +-------------+

Temps total de reconstruction (zero -> Odoo accessible en HTTP) : ~20 minutes
```

Le script **`setup/deploy-all.py`** (lorsqu'il est utilise) enchaine ces phases avec des notifications par **webhook** (succes ou echec), ce qui automatise le deploiement complet et facilite l'integration dans une chaine d'integration ou la supervision humaine.

**Synthese des durees** : creation / clone du template, `terraform apply` (quatre VMs), playbooks Ansible cluster K3s, role deploiement Odoo (NFS + Helm Bitnami + Ingress HTTPS), puis premier acces navigateur. Les variations dependent du reseau, du stockage Proxmox et du pull d'images (Docker Hub / registres Bitnami).
