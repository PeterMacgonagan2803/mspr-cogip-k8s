# Mission 6 : Ansible — Déploiement du cluster K3s

## 1. Objectif

Déployer un cluster Kubernetes K3s composé d'1 control-plane et 2 workers sur les VMs provisionnées par Terraform, de manière entièrement automatisée via Ansible.

## 2. Playbooks et rôles impliqués

```
ansible/
├── playbooks/
│   ├── site.yml            # Orchestrateur principal (appelle tout)
│   └── k3s-cluster.yml     # Déploiement K3s uniquement
└── roles/
    ├── common/             # Configuration de base (toutes les VMs)
    ├── k3s-server/         # Installation du control-plane
    └── k3s-agent/          # Installation des workers
```

## 3. Rôle `common` — Configuration de base

Appliqué à **toutes les VMs** (control-plane, workers, NFS), ce rôle prépare l'environnement :

| Action | Justification |
|--------|---------------|
| Mise à jour APT | Paquets de sécurité à jour |
| Installation paquets (curl, jq, nfs-common...) | Dépendances K3s et NFS |
| Configuration `/etc/hosts` | Résolution de noms entre les noeuds |
| Désactivation du swap | **Requis par Kubernetes** (kubelet refuse de démarrer avec swap actif) |
| Chargement modules noyau (`br_netfilter`, `overlay`) | Requis pour le réseau CNI (Container Network Interface) |
| Configuration sysctl (`ip_forward`, `bridge-nf-call-iptables`) | Permet le routage réseau inter-pods |

## 4. Rôle `k3s-server` — Control-plane

### Installation

```bash
curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION="v1.29.2+k3s1" sh -s - server \
  --write-kubeconfig-mode 644 \
  --tls-san <IP_CONTROL_PLANE> \
  --node-name k3s-control-plane \
  --cluster-init
```

| Paramètre | Explication |
|-----------|-------------|
| `--write-kubeconfig-mode 644` | Rend le kubeconfig lisible pour Ansible/Helm |
| `--tls-san` | Ajoute l'IP au certificat TLS du serveur API |
| `--cluster-init` | Initialise le cluster (mode HA-capable) |

### Actions post-installation

1. **Attente** que K3s soit opérationnel (fichier `/etc/rancher/k3s/k3s.yaml` créé)
2. **Attente** que le noeud passe en état `Ready`
3. **Récupération du token** (`/var/lib/rancher/k3s/server/node-token`) pour les workers
4. **Sauvegarde du kubeconfig** en local (avec IP du serveur au lieu de `127.0.0.1`)
5. **Installation de Helm** sur le control-plane

### Données partagées avec les workers

Le rôle exporte deux variables via `set_fact` :
- `k3s_token` : Token d'authentification pour rejoindre le cluster
- `k3s_server_url` : URL de l'API server (`https://<IP>:6443`)

## 5. Rôle `k3s-agent` — Workers

### Installation

```bash
curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION="v1.29.2+k3s1" sh -s - agent \
  --server https://<IP_CONTROL_PLANE>:6443 \
  --token <K3S_TOKEN> \
  --node-name <WORKER_NAME>
```

### Particularités

- **Exécution séquentielle** (`serial: 1`) : Les workers rejoignent le cluster un par un pour éviter les conflits.
- **Vérification** : Ansible vérifie que chaque worker est bien visible dans `kubectl get nodes` avant de passer au suivant.

## 6. Vérification du cluster

Le playbook `k3s-cluster.yml` se termine par une phase de vérification :

```bash
$ kubectl get nodes -o wide
NAME               STATUS   ROLES                  AGE   VERSION
k3s-control-plane  Ready    control-plane,master   5m    v1.29.2+k3s1
k3s-worker-1       Ready    <none>                 3m    v1.29.2+k3s1
k3s-worker-2       Ready    <none>                 1m    v1.29.2+k3s1

$ kubectl get pods -A
NAMESPACE     NAME                                      READY   STATUS
kube-system   coredns-...                               1/1     Running
kube-system   local-path-provisioner-...                1/1     Running
kube-system   metrics-server-...                        1/1     Running
kube-system   svclb-traefik-...                         2/2     Running
kube-system   traefik-...                               1/1     Running
```

K3s inclut nativement :
- **CoreDNS** : Résolution DNS intra-cluster
- **Traefik** : Ingress Controller (proxy inverse)
- **ServiceLB** : LoadBalancer pour les services de type `LoadBalancer`
- **Metrics Server** : Métriques pour `kubectl top`
- **Local Path Provisioner** : StorageClass locale (complétée par NFS)

## 7. Commandes

```bash
# Déployer uniquement le cluster K3s
ansible-playbook playbooks/k3s-cluster.yml --ask-vault-pass

# Déployer tout (common + NFS + K3s + Odoo)
ansible-playbook playbooks/site.yml --ask-vault-pass
```
