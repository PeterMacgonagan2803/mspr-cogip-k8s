"""Execute une commande SSH sur Proxmox (variables d'environnement obligatoires)."""
import os
import sys

import paramiko

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def ssh_exec(host: str, user: str, password: str, command: str, timeout: int = 900):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username=user, password=password, timeout=10)
    _stdin, stdout, stderr = ssh.exec_command(command, timeout=timeout)
    out = stdout.read().decode()
    err = stderr.read().decode()
    code = stdout.channel.recv_exit_status()
    ssh.close()
    return out, err, code


def main():
    host = os.environ.get("MSPR_PROXMOX_HOST", "").strip()
    password = os.environ.get("MSPR_PROXMOX_PASS", "").strip()
    user = os.environ.get("MSPR_PROXMOX_USER", "root").strip()
    if not host or not password:
        print("Definir MSPR_PROXMOX_HOST et MSPR_PROXMOX_PASS", file=sys.stderr)
        sys.exit(2)
    if len(sys.argv) < 2:
        print("Usage: python remote-exec.py <commande-shell>")
        sys.exit(1)
    cmd = sys.argv[1]
    out, err, code = ssh_exec(host, user, password, cmd)
    if out:
        print(out, end="")
    if err:
        print(err, end="", file=sys.stderr)
    sys.exit(code)


if __name__ == "__main__":
    main()
