#!/usr/bin/env python3
"""
Lance packer build sur Proxmox (création VM + provision) et, en parallèle,
tente SSH ubuntu@10.10.10.99 via le bastion jusqu'à succès.

À exécuter depuis Cursor ou la ligne de commande ; les logs Packer défilent
pendant qu'un fil d'essais SSH confirme la connectivité pendant la fenêtre
avant conversion en template.
"""
from __future__ import annotations

import os
import sys
import threading
import time

import paramiko

BASTION = os.environ.get("MSPR_PROXMOX_HOST", "").strip()
BASTION_USER = os.environ.get("MSPR_PROXMOX_USER", "root").strip()
BASTION_PASS = os.environ.get("MSPR_PROXMOX_PASS", "").strip()
PROXMOX_NODE = os.environ.get("MSPR_PROXMOX_NODE", "pve").strip()
VM_ID = os.environ.get("MSPR_PACKER_VM_ID", "9000").strip()
VM_HOST = "10.10.10.99"
VM_USER = "ubuntu"
VM_PASS = "ubuntu"

if not BASTION or not BASTION_PASS:
    print("Definir MSPR_PROXMOX_HOST et MSPR_PROXMOX_PASS", file=sys.stderr)
    sys.exit(2)


def _remote_packer_cmd() -> str:
    return f"""
set -e
cd /root/mspr-cogip-k8s
git fetch origin && git reset --hard origin/main
HASH=$(openssl passwd -6 ubuntu)
sed -i "s|__UBUNTU_HASH__|${{HASH}}|" packer/http/user-data
echo "=== user-data (debut) ==="
head -35 packer/http/user-data

qm stop {VM_ID} --timeout 20 2>/dev/null || true
sleep 2
qm destroy {VM_ID} --purge 2>/dev/null || true

cd packer
packer init .

export PACKER_LOG=1
export PACKER_LOG_PATH=/tmp/packer-last.log
rm -f /tmp/packer-tee.log

packer build \\
  -var 'proxmox_password={BASTION_PASS}' \\
  -var 'proxmox_node={PROXMOX_NODE}' \\
  -var 'vm_id={VM_ID}' \\
  . 2>&1 | tee /tmp/packer-tee.log

echo "=== qm list ==="
qm list | grep {VM_ID} || true
echo DONE
"""


def ssh_via_bastion_once() -> bool:
    """Une tentative : bastion -> direct-tcpip -> ubuntu@VM. Retourne True si OK."""
    jump = paramiko.SSHClient()
    client = None
    try:
        jump.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        jump.connect(BASTION, username=BASTION_USER, password=BASTION_PASS, timeout=25)
        transport = jump.get_transport()
        if transport is None:
            return False
        chan = transport.open_channel("direct-tcpip", (VM_HOST, 22), ("", 0))
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            VM_HOST,
            username=VM_USER,
            password=VM_PASS,
            sock=chan,
            timeout=18,
            allow_agent=False,
            look_for_keys=False,
            banner_timeout=15,
            auth_timeout=15,
        )
        _, stdout, _ = client.exec_command(
            "echo SSH_VERIFY_OK && hostname && whoami", timeout=25
        )
        out = stdout.read().decode("utf-8", errors="replace")
        if "SSH_VERIFY_OK" not in out:
            return False
        print("\n" + "=" * 60, flush=True)
        print("SSH: connexion reussie pendant le build (via bastion)", flush=True)
        print(out.strip(), flush=True)
        print("=" * 60 + "\n", flush=True)
        return True
    except Exception:
        return False
    finally:
        try:
            if client is not None:
                client.close()
        except Exception:
            pass
        try:
            jump.close()
        except Exception:
            pass


def ssh_poll_worker(stop: threading.Event, out: dict) -> None:
    """Boucle jusqu'à stop ou première connexion SSH réussie."""
    time.sleep(25)
    n = 0
    while not stop.is_set():
        n += 1
        if ssh_via_bastion_once():
            out["ok"] = True
            print(f"[verify-ssh] Succès à la tentative {n}", flush=True)
            return
        if n % 5 == 0:
            print(
                f"[verify-ssh] Tentative {n}... (install / premier boot en cours)",
                flush=True,
            )
        time.sleep(15)


def run_packer_streaming() -> int:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(BASTION, username=BASTION_USER, password=BASTION_PASS, timeout=30)
    print("Proxmox OK — packer build + surveillance SSH démarrent...\n", flush=True)
    _, stdout, stderr = ssh.exec_command(_remote_packer_cmd(), timeout=3600)
    for line in iter(stdout.readline, ""):
        sys.stdout.write(line)
        sys.stdout.flush()
    err = stderr.read().decode("utf-8", errors="replace")
    code = stdout.channel.recv_exit_status()
    ssh.close()
    if err.strip():
        print("STDERR:", err[:2000], flush=True)
    return code


def main() -> None:
    stop = threading.Event()
    result: dict = {"ok": False}
    poller = threading.Thread(target=ssh_poll_worker, args=(stop, result), daemon=True)
    poller.start()
    try:
        code = run_packer_streaming()
    finally:
        stop.set()
    poller.join(timeout=5)

    print(f"\npacker build: code sortie = {code}", flush=True)
    print(f"SSH verifie pendant VM active: {'oui' if result['ok'] else 'non'}", flush=True)
    if code != 0:
        sys.exit(code)
    if not result["ok"]:
        print(
            "Avertissement: aucune connexion SSH observée le temps du build "
            "(réseau, mot de passe, ou fenêtre trop courte). Vérifier les logs ci-dessus.",
            flush=True,
            )
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
