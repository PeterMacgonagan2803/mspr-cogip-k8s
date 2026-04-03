# Mission 3 : Suivi de l'avancement — Tableau Kanban

## Organisation des colonnes

Le Kanban est organisé en 4 colonnes selon la méthodologie recommandée :


| A faire | En cours | Revue Technique | Terminé |
| ------- | -------- | --------------- | ------- |


La **revue technique** est réalisée collectivement lors de sessions régulières pour détecter les oublis et erreurs avant validation.

## État final du Kanban (fin de projet)

### Terminé


| Ticket | Description                                                     | Assigné | Priorité |
| ------ | --------------------------------------------------------------- | ------- | -------- |
| KAN-01 | Analyse du cahier des charges COGIP                             | Équipe  | Haute    |
| KAN-02 | Choix des technologies (K3s, Proxmox, Packer/Terraform/Ansible) | Équipe  | Haute    |
| KAN-03 | Initialisation du dépôt Git + structure projet                  | Dev 1   | Haute    |
| KAN-04 | Template Packer : image Ubuntu 22.04 pour Proxmox               | Dev 1   | Haute    |
| KAN-05 | Terraform : provisionnement des 4 VMs                           | Dev 2   | Haute    |
| KAN-06 | Terraform : génération automatique inventaire Ansible           | Dev 2   | Moyenne  |
| KAN-07 | Ansible : rôle `common` (configuration de base)                 | Dev 3   | Haute    |
| KAN-08 | Ansible : rôle `nfs-server` (stockage persistant)               | Dev 3   | Haute    |
| KAN-09 | Ansible : rôle `k3s-server` (control-plane)                     | Dev 1   | Haute    |
| KAN-10 | Ansible : rôle `k3s-agent` (workers)                            | Dev 1   | Haute    |
| KAN-11 | Ansible : rôle `deploy-odoo` (Helm, cert-manager, NFS prov)     | Dev 2   | Haute    |
| KAN-12 | Ansible : Ingress Traefik HTTPS pour Odoo                       | Dev 2   | Haute    |
| KAN-13 | Ansible Vault : sécurisation des secrets                        | Dev 4   | Moyenne  |
| KAN-14 | CI GitHub Actions : validation IaC automatique                  | Dev 4   | Moyenne  |
| KAN-15 | Health check HTTP : vérification Odoo opérationnel              | Dev 2   | Moyenne  |
| KAN-16 | Playbook de destruction (nettoyage)                             | Dev 3   | Basse    |
| KAN-17 | Tests d'intégration complets                                    | Équipe  | Haute    |
| KAN-18 | Rédaction du dossier de rendu                                   | Équipe  | Haute    |
| KAN-19 | Préparation du support de soutenance                            | Équipe  | Haute    |


## Outil recommandé

Pour un suivi en temps réel durant le projet, nous recommandons **GitHub Projects** (intégré au dépôt) ou **Kanboard** (open-source, auto-hébergé).

Le tableau ci-dessus constitue le snapshot final de l'état du Kanban à la clôture du projet.

> **Note** : Lors de la soutenance, des captures d'écran de l'évolution du Kanban (en cours de projet) devront être présentées pour démontrer le suivi agile.

