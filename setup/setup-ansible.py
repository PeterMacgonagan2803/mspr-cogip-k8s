"""Exemple minimal : executer une commande sur Proxmox via SSH (env MSPR_*)."""
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

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(host, username=user, password=password, timeout=10)
cmd = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "hostname"
_stdin, stdout, stderr = ssh.exec_command(cmd, timeout=300)
print(stdout.read().decode(errors="replace"), end="")
err = stderr.read().decode(errors="replace")
if err:
    print(err, end="", file=sys.stderr)
ssh.close()
