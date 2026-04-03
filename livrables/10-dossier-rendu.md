# Mission 8 : Dossier de rendu final -- MSPR COGIP

## Sommaire

1. [Introduction et contexte](#1-introduction-et-contexte)
2. [Choix des technologies](#2-choix-des-technologies)
3. [Organisation du projet](#3-organisation-du-projet)
4. [Suivi de l'avancement](#4-suivi-de-lavancement)
5. [Mesures d'inclusivite](#5-mesures-dinclusivite)
6. [Preparation des images VM](#6-preparation-des-images)
7. [Terraform -- Deploiement de l'infrastructure](#7-terraform)
8. [Ansible -- Deploiement de Kubernetes](#8-ansible-k3s)
9. [Ansible -- Deploiement d'Odoo](#9-ansible-odoo)
10. [Architecture globale](#10-architecture-globale)
11. [Captures d'ecran et preuves](#11-captures-decran)
12. [Difficultes rencontrees et solutions](#12-difficultes-et-solutions)
13. [Conclusion](#13-conclusion)
14. [Annexes](#14-annexes)

---

## 1. Introduction et contexte

La societe COGIP, specialisee dans les ERP, a decroche un contrat avec le groupe Tesker (vehicules electriques). Notre entreprise a remporte l'appel d'offres pour la mise en place d'une infrastructure hebergeant l'ERP Odoo, repondant aux criteres suivants :

- **Evolutivite** : capacite de dimensionnement facile
- **Performance** : ressources adaptees a Odoo
- **Resilience** : resistance aux pannes
- **Reproductibilite** : Infrastructure as Code pour le PRA

La solution proposee : un cluster **Kubernetes K3s** deploye via **Terraform + Ansible** sur **Proxmox VE** (serveur dedie OVH).

## 2. Choix des technologies

> Detail complet : voir [01-choix-technologies.md](./01-choix-technologies.md)

**Resume** :

- **K3s** : Distribution K8s legere, certifiee CNCF, avec LoadBalancer et Ingress Traefik integres
- **Proxmox VE** : Hyperviseur open-source avec API REST complete
- **Cloud-init** : Templates VM reproductibles (alternative legere a Packer)
- **Terraform** : Provisionnement declaratif de l'infrastructure (provider `bpg/proxmox`)
- **Ansible** : Configuration agentless et deploiement applicatif
- **NFS** : Stockage persistant leger pour le PoC
- **cert-manager** : **Optionnel** -- gestion des certificats TLS (autosignes pour le PoC) ; desactive par defaut (`enable_cert_manager=false`) pour eviter une dependance critique au registre quay.io en cas d'indisponibilite ; a activer lorsque l'on souhaite exposer Odoo en HTTPS avec emission automatique de certificats

## 3. Organisation du projet

> Detail complet : voir [02-gantt.md](./02-gantt.md)

Le projet a ete decoupe en **15 taches** reparties sur les 19 heures de preparation. Un diagramme de Gantt (format Mermaid) detaille le planning previsionnel et les dependances entre taches.

**Automatisation bout en bout** : le depot inclut le script `**setup/deploy-all.py`**, qui orchestre le deploiement complet (phases template / infrastructure / Ansible / verification) et envoie des **notifications webhook** en cas de succes ou d'echec, ce qui documente la chaine operationnelle et permet une supervision sans rester colle au terminal.

## 4. Suivi de l'avancement

> Detail complet : voir [03-kanban.md](./03-kanban.md)

Un tableau Kanban a 4 colonnes (A faire -> En cours -> Revue Technique -> Termine) a ete utilise pour suivre les 19 tickets du projet. La revue technique a ete realisee collectivement.

## 5. Mesures d'inclusivite

> Detail complet : voir [04-inclusivite.md](./04-inclusivite.md)

Des mesures concretes ont ete definies pour :

- L'accueil de personnes en situation de handicap (psychomoteur, visuel)
- La gestion multiculturelle
- L'equilibre vie professionnelle / vie privee
- La collaboration avec le referent handicap

## 6. Preparation des images

> Detail complet : voir [05-packer.md](./05-packer.md)

Template VM Ubuntu 22.04 LTS cree via image cloud officielle + cloud-init, convertie en template Proxmox (ID 9000). Les fichiers Packer sont conserves comme approche alternative documentee.

## 7. Terraform

> Detail complet : voir [06-terraform.md](./06-terraform.md)

Deploiement de 4 VMs via `for_each` avec generation automatique de l'inventaire Ansible. Provider `bpg/proxmox`.


| VM           | CPU | RAM  | Disque    | Role          |
| ------------ | --- | ---- | --------- | ------------- |
| k3s-server   | 2   | 4 Go | **30 Go** | Control-plane |
| k3s-worker-1 | 2   | 4 Go | **30 Go** | Worker        |
| k3s-worker-2 | 2   | 4 Go | **30 Go** | Worker        |
| nfs-server   | 1   | 1 Go | **50 Go** | Stockage NFS  |


Les disques **30 Go** sur les noeuds K3s offrent une marge suffisante pour les couches systeme, etcd, kubelet et le pull d'images. Le serveur NFS en **50 Go** dimensionne le stockage persistant partage (donnees Odoo et PostgreSQL) pour le PoC.

## 8. Ansible -- K3s

> Detail complet : voir [07-ansible-k3s.md](./07-ansible-k3s.md)

Deploiement automatise du cluster K3s (1 control-plane + 2 workers) via 3 roles Ansible.

## 9. Ansible -- Odoo

> Detail complet : voir [08-ansible-odoo.md](./08-ansible-odoo.md)

Le role de deploiement applique notamment :

- **NFS Provisioner** via Helm (`nfs-subdir-external-provisioner`) pour la `StorageClass` dynamique
- **Odoo 18** et **PostgreSQL 17** via **manifests Kubernetes natifs** (Deployments, Services, PVC, Ingress) et images officielles **docker.io** (`odoo:18`, `postgres:17`) -- **sans** chart Helm Bitnami pour la couche applicative Odoo / base de donnees
- **Ingress Traefik** en **HTTP** par defaut (`http://odoo.local` vers le service Odoo)
- **cert-manager** : **optionnel**, conditionne par la variable Ansible `enable_cert_manager` (defaut `false`) ; lorsqu'il est active, Helm installe cert-manager et les ressources TLS associees (ClusterIssuer autosigne, etc.)

Cette separation permet de garder un chemin de deploiement stable meme lorsque les registres tiers (par exemple quay.io pour certaines images de cert-manager) subissent des erreurs transitoires.

## 10. Architecture globale

> Detail complet : voir [09-architecture.md](./09-architecture.md)

Schema complet de l'architecture reseau (NAT, vmbr1, port-forwarding), des flux, des composants Kubernetes deployes, des tailles de disques (30 Go / 50 Go) et du chemin d'acces HTTP par defaut.

## 11. Captures d'ecran

Les captures ci-dessous illustrent les preuves de deploiement ; les fichiers image peuvent etre ajoutes dans un dossier `livrables/screenshots/` ou equivalent et references par lien Markdown si le rendu PDF ou la plateforme le permet.

### 11.1 Proxmox -- VMs deployees

**Description** : Vue de l'interface Proxmox montrant les **quatre machines virtuelles** (control-plane, deux workers, NFS) avec leurs adresses IP sur `vmbr1`, etats allumees, et repartition des ressources (CPU, RAM, disques 30 Go / 50 Go).

### 11.2 kubectl get nodes

**Description** : Sortie du terminal avec la commande `kubectl get nodes -o wide` executee sur le control-plane (ou via kubeconfig), affichant les **trois noeuds** du cluster en etat **Ready**, avec leurs roles (control-plane / worker) et adresses internes.

### 11.3 kubectl get pods -A

**Description** : Sortie de `kubectl get pods -A` listant l'ensemble des pods par namespace : `kube-system` (CoreDNS, Traefik, metrics-server, etc.), `storage` (NFS provisioner), `odoo` (PostgreSQL et Odoo en Running), et eventuellement `cert-manager` **uniquement** si la variable `enable_cert_manager` a ete activee pour la capture.

### 11.4 Interface Odoo accessible

**Description** : Capture du navigateur sur `**http://odoo.local`** (ou l'hote equivalent) affichant l'**ecran de connexion ou le tableau de bord Odoo**, confirmant que l'Ingress Traefik route correctement le trafic HTTP vers le service applicatif.

### 11.5 Terraform apply

**Description** : Extrait de la sortie `**terraform apply`** montrant la creation ou la mise a jour des **quatre ressources VM** Proxmox, sans erreur, avec resume des adresses IP et disques provisionnes.

### 11.6 Ansible playbook

**Description** : Extrait de la sortie du playbook principal (`**site.yml`** ou enchainement des playbooks K3s puis Odoo) montrant les taches **changed / ok** jusqu'au resume **PLAY RECAP** sans echec, validant l'idempotence ou le premier deploiement reussi.

## 12. Difficultes rencontrees et solutions


| Difficulte                                                                                                                               | Solution apportee                                                                                                                                                                                                                                                |
| ---------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Provider Terraform `telmate/proxmox` : erreurs de permissions (`VM.Monitor`) meme avec des tokens privilegies                            | Migration vers le provider `bpg/proxmox` qui gere mieux l'authentification par mot de passe et le SSH natif                                                                                                                                                      |
| Packer : echec de l'autoinstall Ubuntu (l'installeur manuel se lancait au lieu du mode cloud-init)                                       | Abandon de Packer + ISO au profit d'un script utilisant l'image cloud Ubuntu qcow2 avec cloud-init natif                                                                                                                                                         |
| Images Docker Bitnami Odoo : tags obsoletes non disponibles sur Docker Hub                                                               | Remplacement du chart Helm Bitnami par des **manifests Kubernetes natifs** avec les images officielles `odoo:18` et `postgres:17`                                                                                                                                |
| Timeout SSH lors de l'execution d'Ansible depuis Windows vers les VMs via Proxmox                                                        | Execution d'Ansible directement sur le serveur Proxmox (plus proche des VMs) avec scripts Python/Paramiko pour l'orchestration                                                                                                                                   |
| Traefik retournait 404 en HTTP : l'Ingress ne routait que le trafic HTTPS (`websecure`)                                                  | Ajout d'un IngressRoute Traefik CRD pour le trafic HTTP (`web`) en complement de l'Ingress standard                                                                                                                                                              |
| QEMU Guest Agent : Terraform bloquait indefiniment en attendant l'agent non installe                                                     | Desactivation de l'agent dans la configuration Terraform (`agent { enabled = false }`)                                                                                                                                                                           |
| Reseau Proxmox : VMs sur reseau prive non accessibles depuis l'exterieur                                                                 | Configuration NAT avec `vmbr1` (bridge prive) et regles iptables pour le port-forwarding (80, 443)                                                                                                                                                               |
| **Registre quay.io indisponible ou erreurs HTTP 502** lors du pull d'images necessaires a **cert-manager**, bloquant le deploiement Helm | **cert-manager rendu optionnel** : variable `enable_cert_manager` par defaut a `false` ; deploiement par defaut en **HTTP** via Traefik sans dependre de quay.io pour le PoC ; reactivation de cert-manager et HTTPS lorsque l'infrastructure externe est stable |


## 13. Conclusion

Ce projet a permis de mettre en place une infrastructure complete et entierement automatisee pour heberger l'ERP Odoo sur un cluster Kubernetes K3s. La solution proposee repond aux exigences de la COGIP :

- **Evolutivite** : Ajout de workers via simple modification Terraform
- **Resilience** : Kubernetes redemarre automatiquement les pods en cas de panne
- **Reproductibilite** : PRA estime a **environ 20 minutes** depuis zero (template, Terraform, Ansible K3s, Ansible Odoo, initialisation), documente dans l'architecture et aligne sur les mesures reelles de deploiement
- **Securite** : Secrets proteges (Ansible Vault), acces SSH par cle ; **acces applicatif en HTTP par defaut** (`http://odoo.local`) pour le PoC ; **HTTPS et cert-manager disponibles mais optionnels** selon `enable_cert_manager`

Le script **deploy-all.py** (`setup/deploy-all.py`) et les webhooks associes materialisent la demarche d'automatisation et de tracabilite demandee dans un contexte professionnel ou pedagogique.

## 14. Annexes

Les codes sources complets sont disponibles dans le depot Git :

- **Depot Git** : URL du depôt équipe (GitHub / GitLab / Gitea — à indiquer lors du rendu)
- `setup/` : Scripts de deploiement (template VM, configuration reseau, outils, **deploy-all.py** avec notifications webhook)
- `terraform/` : Recettes Terraform (provider `bpg/proxmox`, VMs, inventaire ; disques **30 Go** K3s, **50 Go** NFS)
- `ansible/` : Playbooks et roles Ansible
  - `playbooks/site.yml` : Orchestrateur principal
  - `roles/k3s-server/` : Role control-plane
  - `roles/k3s-agent/` : Role workers
  - `roles/deploy-odoo/` : Deploiement Odoo + PostgreSQL via manifests K8s officiels ; NFS provisioner ; cert-manager conditionnel
- `packer/` : Approche alternative Packer (conservee pour reference)
- `livrables/` : Documentation detaillee par mission

