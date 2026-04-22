# Mission 7 : Ansible — Déploiement d’Odoo et Ingress HTTPS

## 1. Objectif

Déployer l’ERP **Odoo** sur le cluster **K3s** avec stockage persistant **NFS**, en utilisant les modules **Ansible Galaxy** `kubernetes.core` (notamment **`helm`**), comme recommandé dans le sujet TPRE961. L’accès se fait en **HTTPS** avec un **certificat TLS autosigné** généré par le chart Helm (**`ingress.selfSigned: true`**), ce qui produit l’avertissement navigateur attendu pour un PoC.

## 2. Chaîne de déploiement

```
NFS Provisioner (Helm)  →  Chart bitnami/odoo (Helm)  →  Ingress Traefik (K3s) + TLS autosigné
```

## 3. NFS Subdir External Provisioner

Identique au scénario « bare metal » du sujet : `StorageClass` `nfs-client` pointant vers la VM NFS.

- Rôle Ansible : `roles/deploy-odoo` (tâches Helm + dépôt `nfs-subdir-external-provisioner`).
- Chart : `nfs-subdir-external-provisioner/nfs-subdir-external-provisioner`.

## 4. Odoo (Bitnami) via Helm

- Dépôt : `https://charts.bitnami.com/bitnami`
- Release : `odoo`, namespace `odoo`
- **PostgreSQL** est fourni par le chart (sous-chart Bitnami).
- **Persistance** : `global.defaultStorageClass` / `persistence.storageClass` = `nfs-client`.
- **Ingress** : `ingressClassName: traefik`, `tls: true`, `selfSigned: true`, annotations Traefik **`web` et `websecure`** (HTTP **et** HTTPS vers la même règle ; le guide peut citer `http://odoo.local` ou `https://odoo.local`).
- **Service** : `ClusterIP` (sur K3s sans cloud-controller, un `LoadBalancer` reste indéfiniment `<pending>` et bloque `helm --wait` ; l’accès utilisateur passe par **Traefik / Ingress**).
- **Images conteneurs** : depuis la migration des images Bitnami sur Docker Hub, les tags référencés par le chart peuvent être **absents** de `docker.io/bitnami/*`. Le dépôt **Docker Hub `bitnamilegacy`** conserve les mêmes tags ; le rôle fixe `image.repository` / `postgresql.image.repository` et `global.security.allowInsecureImages: true` (exigence du chart lorsque le dépôt n’est pas strictement `bitnami/`).
- **NFS provisioner** : un `nodeSelector` peut placer le pod provisioner sur un nœud donné (ex. éviter un worker avec AppArmor / paquets système dégradés).
- **Timeouts Helm** : délais portés à **20 minutes** pour le premier pull d’images sur un cluster TP.

Les mots de passe applicatifs sont pilotés par `group_vars` (`odoo_bitnami_admin_password`, `odoo_bitnami_pg_password`), avec possibilité de surcharge via **Ansible Vault** (`vault.yml`).

## 5. Fichiers concernés

| Élément | Emplacement |
|---------|-------------|
| Playbook | `ansible/playbooks/deploy-odoo.yml` |
| Rôle | `ansible/roles/deploy-odoo/` |
| Valeurs Helm Odoo | `templates/odoo-bitnami-values.yml.j2` |
| Valeurs NFS | `templates/nfs-values.yml.j2` |

## 6. Vérifications

```bash
kubectl get pods -n odoo
kubectl get ingress -n odoo
curl -sk -H 'Host: odoo.local' https://<IP-control-plane>/
```

## 7. Destruction / nettoyage

Le playbook `playbooks/destroy.yml` supprime les releases Helm `odoo` et `nfs-provisioner`, puis les namespaces concernés.
