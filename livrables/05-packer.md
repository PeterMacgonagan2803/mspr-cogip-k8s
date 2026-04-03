# Mission 4 : Preparation des images VM (Template Cloud-init)

## 1. Objectif

Creer un **template de VM Ubuntu 22.04 LTS** standardise sur Proxmox, pre-configure avec cloud-init. Ce template (ID 9000) sert de base a toutes les VMs du cluster, clonees ensuite par Terraform.

## 2. Pourquoi un template standardise ?

Sans template, chaque VM devrait etre installee manuellement et configuree individuellement. Avec un template :

- **Reproductibilite** : Le meme template est utilise pour toutes les VMs, garantissant une base identique.
- **PRA** : En cas de sinistre, le template peut etre recree en quelques minutes depuis le script.
- **Gain de temps** : Les paquets sont pre-installes, reduisant le temps de provisionnement Ansible.
- **Versionnement** : Le script de creation est versionne dans Git.

## 3. Approche retenue : Image Cloud Ubuntu + cloud-init

Plutot qu'une installation ISO classique via Packer (plus longue, dependante d'un serveur HTTP pour l'autoinstall), nous utilisons directement l'**image cloud officielle Ubuntu** au format qcow2, qui supporte nativement cloud-init.

### Avantages par rapport a Packer + ISO

| Critere | Packer + ISO | Image Cloud + Script |
|---------|-------------|---------------------|
| Temps de creation | ~15-20 min | ~3 min |
| Dependances | Packer + serveur HTTP | Script bash uniquement |
| Taille image | ~2 Go (ISO) | ~700 Mo (qcow2) |
| Complexite | Elevee (autoinstall, boot config) | Faible (telechargement + qm commands) |
| Reproductibilite | Excellente | Excellente |

### Note sur Packer

Les fichiers Packer (`packer/`) sont conserves dans le depot comme approche alternative documentee. Ils fonctionnent pour des environnements ou l'image cloud n'est pas disponible.

## 4. Structure des fichiers

```
setup/
  create-template.sh     # Script principal de creation du template
packer/                   # Approche alternative (conservee pour reference)
  ubuntu-k3s.pkr.hcl     # Configuration Packer
  variables.pkr.hcl      # Variables Packer
  http/
    user-data             # Cloud-init autoinstall
    meta-data             # Metadonnees cloud-init
```

## 5. Fonctionnement du script `create-template.sh`

### Phase 1 : Telechargement de l'image cloud

```bash
wget https://cloud-images.ubuntu.com/jammy/current/jammy-server-cloudimg-amd64.img
```

L'image officielle Ubuntu 22.04 LTS (Jammy) au format qcow2, optimisee pour les environnements virtualises.

### Phase 2 : Creation et configuration de la VM

| Parametre | Valeur |
|-----------|--------|
| VM ID | 9000 |
| OS | Ubuntu 22.04 LTS (cloud image) |
| CPU | 2 coeurs, type `host` |
| RAM | 2048 Mo |
| Disque | Import de l'image qcow2 |
| Reseau | virtio, bridge `vmbr1` |
| Cloud-init | Active (lecteur IDE2) |
| Boot | Disque SCSI uniquement |

### Phase 3 : Configuration cloud-init par defaut

```bash
qm set 9000 --ciuser ubuntu
qm set 9000 --ipconfig0 ip=dhcp
qm set 9000 --agent enabled=1
```

- Utilisateur `ubuntu` cree automatiquement au premier boot
- IP configurable via cloud-init (Terraform injecte l'IP statique au clonage)
- QEMU Guest Agent active pour l'integration Proxmox

### Phase 4 : Conversion en template

```bash
qm template 9000
```

La VM est convertie en template Proxmox, pret a etre clone par Terraform via `clone { vm_id = 9000 }`.

## 6. Commandes d'utilisation

```bash
# Sur le serveur Proxmox (en SSH root)
bash create-template.sh
```

Ou telecharger depuis le depot :

```bash
# Depuis votre clone du depôt MSPR :
#   bash setup/create-template.sh
```

## 7. Interet pour le PRA de la COGIP

En cas de perte de l'infrastructure, le template VM peut etre recree en **~3 minutes** depuis le script versionne. Combine avec Terraform et Ansible, l'ensemble de l'infrastructure est reconstituable sans intervention manuelle, satisfaisant l'exigence de PRA du client Tesker.
