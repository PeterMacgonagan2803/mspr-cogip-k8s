"""SSH vers Proxmox — meme contrat que remote-exec.py (variables d'environnement)."""
import os
import sys

import paramiko

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

host = os.environ.get("MSPR_PROXMOX_HOST", "").strip()
password = os.environ.get("MSPR_PROXMOX_PASS", "").strip()
user = os.environ.get("MSPR_PROXMOX_USER", "root").strip()
if not host or not password:
    print("Definir MSPR_PROXMOX_HOST et MSPR_PROXMOX_PASS", file=sys.stderr)
    sys.exit(2)
if len(sys.argv) < 2:
    print("Usage: python remote-bg.py <commande>")
    sys.exit(1)

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(host, username=user, password=password, timeout=10)
ssh.exec_command(sys.argv[1])
ssh.close()
