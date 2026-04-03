#!/usr/bin/env python3
"""
Validation MSPR : Packer sur Proxmox jusqu'à succès, notifications webhook (Google Chat),
sonde SSH Proxmox (qm list) pendant le build.

Variables d'environnement :
  MSPR_WEBHOOK_URL   — surcharge l'URL (sinon lue depuis deploy-all.py)
  MSPR_PACKER_MAX_ATTEMPTS — nombre max de builds complets (défaut : 50)
  MSPR_POLL_SEC      — intervalle entre rapports VM sur webhook (défaut : 90)
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
import threading
import time
import urllib.request
from pathlib import Path

import paramiko

# Évite le bruit Paramiko / libssh sur stderr (ex. « Secsh channel ... refused ») sous PowerShell.
logging.getLogger("paramiko").setLevel(logging.CRITICAL)

HOST = os.environ.get("MSPR_PROXMOX_HOST", "").strip()
USER = os.environ.get("MSPR_PROXMOX_USER", "root").strip()
PASS = os.environ.get("MSPR_PROXMOX_PASS", "").strip()
VM_ID = os.environ.get("MSPR_PACKER_VM_ID", "9002")
VM_HOST = "10.10.10.99"
VM_USER = "ubuntu"
VM_PASS = "ubuntu"
NODE = os.environ.get("MSPR_PROXMOX_NODE", "pve").strip()
if not HOST or not PASS:
    print("Definir MSPR_PROXMOX_HOST et MSPR_PROXMOX_PASS", file=sys.stderr)
    sys.exit(2)

MAX_ATTEMPTS = int(os.environ.get("MSPR_PACKER_MAX_ATTEMPTS", "50"))
POLL_SEC = int(os.environ.get("MSPR_POLL_SEC", "90"))
PACKER_SSH_TIMEOUT = int(os.environ.get("MSPR_PACKER_SSH_TIMEOUT", "7200"))


def load_webhook_url() -> str:
    env = os.environ.get("MSPR_WEBHOOK_URL", "").strip()
    if env:
        return env
    deploy = Path(__file__).resolve().parent / "deploy-all.py"
    if not deploy.is_file():
        return ""
    text = deploy.read_text(encoding="utf-8")
    m = re.search(r'^WEBHOOK_URL\s*=\s*"([^"]+)"', text, re.MULTILINE)
    return m.group(1) if m else ""


WEBHOOK_URL = load_webhook_url()


def notify(text: str) -> None:
    print(text.replace("*", ""), flush=True)
    if not WEBHOOK_URL:
        return
    data = json.dumps({"text": text}).encode("utf-8")
    req = urllib.request.Request(
        WEBHOOK_URL,
        data=data,
        headers={"Content-Type": "application/json; charset=UTF-8"},
    )
    try:
        urllib.request.urlopen(req, timeout=15)
    except Exception as e:
        print(f"[notify] webhook erreur: {e}", flush=True)


def ssh_connect() -> paramiko.SSHClient:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, username=USER, password=PASS, timeout=25)
    return ssh


def fetch_vm_snapshot() -> str:
    try:
        ssh = ssh_connect()
        cmd = (
            f"echo '=== {NODE} ===' && date -u '+%Y-%m-%d %H:%M:%S UTC' && "
            f"qm list && echo '--- VM {VM_ID} ---' && "
            f"(qm status {VM_ID} 2>/dev/null || echo 'VM {VM_ID} absente')"
        )
        _, stdout, stderr = ssh.exec_command(cmd, timeout=35)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        ssh.close()
        if err.strip():
            out += "\nstderr: " + err[:500]
        return out.strip()[:3800]
    except Exception as e:
        return f"Erreur sonde Proxmox: {e}"


REMOTE_PACKER_CMD = f"""
set -e
cd /root/mspr-cogip-k8s
git fetch origin && git reset --hard origin/main
HASH=$(openssl passwd -6 ubuntu)
sed -i "s|__UBUNTU_HASH__|${{HASH}}|" packer/http/user-data

# Packer échoue si vm_id existe déjà ; ne pas masquer un destroy raté (|| true).
if qm config {VM_ID} >/dev/null 2>&1; then
  qm stop {VM_ID} --timeout 45 2>/dev/null || true
  sleep 3
  for n in 1 2 3 4 5 6; do
    qm destroy {VM_ID} --purge 2>/dev/null && break
    qm stop {VM_ID} --timeout 30 2>/dev/null || true
    sleep 2
  done
  if qm config {VM_ID} >/dev/null 2>&1; then
    echo "ERREUR: VM {VM_ID} toujours presente apres destroy (verrou qm / tache en cours?)"
    qm list | grep {VM_ID} || true
    exit 1
  fi
fi

cd packer
packer init .

export PACKER_LOG=1
export PACKER_LOG_PATH=/tmp/packer-last.log
rm -f /tmp/packer-tee.log

set +e
set -o pipefail
packer build \\
  -var 'proxmox_password={PASS}' \\
  -var 'proxmox_node={NODE}' \\
  -var 'vm_id={VM_ID}' \\
  . 2>&1 | tee /tmp/packer-tee.log
RC=${{PIPESTATUS[0]}}
set -e

echo "=== qm list (fin) ==="
qm list | grep {VM_ID} || true
exit $RC
"""


def ssh_via_bastion_once() -> bool:
    jump = paramiko.SSHClient()
    client = None
    try:
        jump.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        jump.connect(HOST, username=USER, password=PASS, timeout=25)
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
            "echo SSH_OK && hostname && whoami", timeout=20
        )
        out = stdout.read().decode("utf-8", errors="replace")
        return "SSH_OK" in out
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


def poll_proxmox_loop(stop: threading.Event) -> None:
    while not stop.wait(POLL_SEC):
        snap = fetch_vm_snapshot()
        notify(f"*MSPR — Surveillance Proxmox*\n```\n{snap}\n```")


def ssh_verify_loop(stop: threading.Event, out: dict) -> None:
    time.sleep(20)
    n = 0
    while not stop.is_set():
        n += 1
        if ssh_via_bastion_once():
            out["ok"] = True
            notify("*MSPR — SSH template OK* (`ubuntu@10.10.10.99` joignable)")
            return
        time.sleep(20)


def _write_stdout_line(line: str) -> None:
    """Évite UnicodeEncodeError sous Windows (cp1252) si Packer affiche → ou autre hors latin-1."""
    try:
        sys.stdout.write(line)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "utf-8"
        sys.stdout.buffer.write(line.encode(enc, errors="replace"))
    sys.stdout.flush()


def run_packer_once() -> int:
    ssh = ssh_connect()
    _, stdout, stderr = ssh.exec_command(REMOTE_PACKER_CMD, timeout=PACKER_SSH_TIMEOUT)
    for line in iter(stdout.readline, ""):
        _write_stdout_line(line)
    err = stderr.read().decode("utf-8", errors="replace")
    code = stdout.channel.recv_exit_status()
    ssh.close()
    if err.strip():
        print("STDERR:", err[:1500], flush=True)
    return code


def main() -> None:
    if not WEBHOOK_URL:
        notify("(MSPR_WEBHOOK_URL absent et deploy-all introuvable — logs console uniquement)")

    notify(
        f"*MSPR — Validation Packer démarrée*\n"
        f"Hôte `{HOST}`, VM build `{VM_ID}`, max tentatives `{MAX_ATTEMPTS}`, poll `{POLL_SEC}s`."
    )

    attempt = 0
    while attempt < MAX_ATTEMPTS:
        attempt += 1
        notify(f"*MSPR — Packer tentative {attempt}/{MAX_ATTEMPTS}*\n`git reset` + build sur Proxmox…")

        stop_poll = threading.Event()
        stop_ssh = threading.Event()
        ssh_result: dict = {"ok": False}

        poller = threading.Thread(target=poll_proxmox_loop, args=(stop_poll,), daemon=True)
        ssh_watcher = threading.Thread(target=ssh_verify_loop, args=(stop_ssh, ssh_result), daemon=True)
        poller.start()
        ssh_watcher.start()

        try:
            code = run_packer_once()
        finally:
            stop_poll.set()
            stop_ssh.set()

        time.sleep(2)
        final_snap = fetch_vm_snapshot()
        notify(f"*MSPR — Fin tentative {attempt}* (code shell distant `{code}`)\n```\n{final_snap[:3000]}\n```")

        if code == 0:
            notify(
                "*MSPR — Packer VALIDÉ*\n"
                "Template construit avec succès. Build considéré comme **validé** pour cette chaîne."
            )
            sys.exit(0)

        notify(
            f"*MSPR — Échec tentative {attempt}*\n"
            f"Code `{code}`. Nouvelle tentative dans 120s (sauf si max atteint)."
        )
        if attempt < MAX_ATTEMPTS:
            time.sleep(120)

    notify(
        f"*MSPR — Abandon après {MAX_ATTEMPTS} tentatives*\n"
        "Vérifier `/tmp/packer-last.log` sur Proxmox et la console ci-dessus."
    )
    sys.exit(1)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(errors="replace")
        except Exception:
            pass
    main()
