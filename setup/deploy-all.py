"""
MSPR TPRE961 (projet COGIP) — orchestration Proxmox, Terraform, Ansible, Odoo.

  Lanceurs Windows (depuis setup/) :
    .\\mspr-deploiement-complet.ps1   deploiement complet (recommande, cf. GUIDE-DEMARRAGE.md)
    .\\mspr-reprise-ansible.ps1       reprise etape Ansible uniquement (MSPR_FROM_STEP=5)

  Equivalents : python deploy-all.py

  Variables obligatoires : MSPR_PROXMOX_HOST, MSPR_PROXMOX_PASS, MSPR_GIT_URL
  Variables utiles : MSPR_FORCE_PACKER, MSPR_RESTART_VMS, MSPR_FROM_STEP, MSPR_WEBHOOK_URL
"""
import paramiko
import sys
import os
import time
import json
import re
import base64
import urllib.request
import subprocess
from pathlib import Path

os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["PYTHONUNBUFFERED"] = "1"
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

USER = "root"


def _require_env(name: str) -> str:
    v = os.environ.get(name, "").strip()
    if not v:
        print(f"ERREUR: variable d'environnement requise — {name}", flush=True)
        sys.exit(1)
    return v


HOST = _require_env("MSPR_PROXMOX_HOST")
PASS = _require_env("MSPR_PROXMOX_PASS")
PROXMOX_NODE = os.environ.get("MSPR_PROXMOX_NODE", "pve")
PACKER_TEMPLATE_VMID = int(os.environ.get("MSPR_PACKER_TEMPLATE_VMID", "9000"))
REMOTE_REPO_DIR = os.environ.get("MSPR_REMOTE_DIR", "mspr-cogip-k8s").strip().strip("/")
MSPR_GIT_URL = os.environ.get("MSPR_GIT_URL", "").strip()
WEBHOOK_URL = os.environ.get("MSPR_WEBHOOK_URL", "").strip()

# Apres clone Terraform : evite pic I/O simultane (io-error QEMU sur worker-2, etc.).
PROXMOX_STAGGER_START = """
set +e
for vmid in 200 201 202 203; do
  qm config "$vmid" >/dev/null 2>&1 || continue
  qm stop "$vmid" --timeout 95 2>/dev/null
done
sleep 10
for vmid in 200 201 202 203; do
  qm config "$vmid" >/dev/null 2>&1 || continue
  qm start "$vmid" && echo "started $vmid" || echo "start_fail $vmid"
  sleep 42
done
rm -f /var/lock/pve-manager/pve-storage-*
echo "STAGGER_START_OK"
"""

# Reprise : uniquement les VM en etat io-error.
PROXMOX_IO_RECOVER = """
set +e
for vmid in 200 201 202 203; do
  qm config "$vmid" >/dev/null 2>&1 || continue
  st=$(qm status "$vmid" 2>/dev/null || true)
  if echo "$st" | grep -qi 'io-error'; then
    echo "recover vmid=$vmid ($st)"
    qm stop "$vmid" --timeout 95 2>/dev/null
    sleep 8
    qm start "$vmid"
    sleep 40
  fi
done
rm -f /var/lock/pve-manager/pve-storage-*
echo "IO_RECOVER_OK"
"""

# Sondes SSH Proxmox -> VMs : journal par IP, delais bornes. ssh_run timeout doit rester > 36*8s * 4.
PROXMOX_SSH_PROBE_ALL = """
set -e
rm -f /root/.ssh/known_hosts
ALL_OK=true
MAX=36
SLEEP=8
for ip in 10.10.10.10 10.10.10.11 10.10.10.12 10.10.10.13; do
    echo ">>> SSH: test $ip (max ${MAX} essais, ${SLEEP}s entre chaque)"
    OK=false
    i=0
    while [ "$i" -lt $MAX ]; do
        i=$((i + 1))
        if ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 -o BatchMode=yes \\
            -i /root/.ssh/id_ansible ubuntu@$ip "echo OK" 2>/dev/null; then
            echo "$ip: SSH OK (essai $i/$MAX)"
            OK=true
            break
        fi
        if [ $((i % 5)) -eq 0 ]; then
            echo "    $ip ... attente ($i/$MAX)"
        fi
        sleep $SLEEP
    done
    if [ "$OK" = "false" ]; then
        echo "$ip: SSH FAIL apres $MAX essais"
        ALL_OK=false
    fi
done
if [ "$ALL_OK" = "false" ]; then
    exit 1
fi
echo "ALL_SSH_OK"
"""

# Depôt Git : epingles apt (nfs-kernel-server=... vs nfs-common .2) — tout ansible/, .yml + .yaml, espaces autour de =
# Reprise : clone souvent vieux (pas de pull) ; le main GitHub peut deja etre sans pin — git pull + ce patch.
_PATCH_NFS_PY = r"""import pathlib,re
root = pathlib.Path("/root/mspr-cogip-k8s/ansible")
if not root.is_dir():
    print("PATCH_NFS_APT_SKIP_NO_ANSIBLE")
    raise SystemExit(0)
# Version apt : tout sauf fin de token YAML (espace, virgule, retour ligne)
rx=re.compile(r"(nfs-kernel-server|nfs-common)\s*=\s*[^\s,#\n\r]+")
n=0
paths=list(root.rglob("*.yml"))+list(root.rglob("*.yaml"))
for path in paths:
    if not path.is_file():
        continue
    t=path.read_text(encoding="utf-8",errors="replace")
    o=t
    t=rx.sub(r"\1",t)
    if t!=o:
        path.write_text(t,encoding="utf-8")
        n+=1
        print("patched",path)
print("PATCH_NFS_APT_OK",n,"files")
"""


def _patch_nfs_apt_remote_sh():
    b64 = base64.b64encode(_PATCH_NFS_PY.encode("utf-8")).decode("ascii")
    # printf evite echo -xxx si le base64 commence par un tiret ; alphabet base64 sans '
    return "set -e\nprintf '%s' '" + b64 + "' | base64 -d | python3\n"


def _nfs_server_tasks_main_overwrite_sh():
    """Copie la tache NFS sans epingle apt depuis ce depot (MSPR/ansible) vers Proxmox."""
    local_main = Path(__file__).resolve().parent.parent / "ansible" / "roles" / "nfs-server" / "tasks" / "main.yml"
    if not local_main.is_file():
        raise FileNotFoundError(
            "ansible/roles/nfs-server/tasks/main.yml introuvable (racine MSPR au-dessus de setup/)."
        )
    b64 = base64.b64encode(local_main.read_bytes()).decode("ascii")
    dest = f"/root/{REMOTE_REPO_DIR}/ansible/roles/nfs-server/tasks/main.yml"
    return (
        "set -e\n"
        f"mkdir -p /root/{REMOTE_REPO_DIR}/ansible/roles/nfs-server/tasks\n"
        f"printf '%s' '{b64}' | base64 -d > {dest}\n"
        f"if grep -qE 'nfs-kernel-server=|nfs-common=' '{dest}'; then\n"
        "  echo 'NFS_MAIN_YML_STILL_PINNED'\n"
        "  exit 1\n"
        "fi\n"
        "echo 'NFS_MAIN_YML_OVERWRITE_OK'\n"
    )


def _combined_nfs_repo_fix_sh():
    return _patch_nfs_apt_remote_sh().strip() + "\n" + _nfs_server_tasks_main_overwrite_sh().strip() + "\n"


PATCH_REPO_NFS_APT_PINS = _combined_nfs_repo_fix_sh()

# Reprise partielle : ex. MSPR_FROM_STEP=5 pour sauter reset/packer/terraform/setup long
# MSPR_RESTART_VMS=202 : reboot/reset ces VMIDs sur Proxmox avant la prep Ansible (virgules ok)
FROM_STEP = max(1, min(7, int(os.environ.get("MSPR_FROM_STEP", "1"))))
RESTART_VMS = os.environ.get("MSPR_RESTART_VMS", "").strip()
FORCE_PACKER = os.environ.get("MSPR_FORCE_PACKER", "").strip().lower() in ("1", "true", "yes", "on")

TOTAL_START = time.time()
step_times = {}

def elapsed():
    return time.time() - TOTAL_START

def fmt(seconds):
    m, s = divmod(int(seconds), 60)
    return f"{m}m{s:02d}s"

def log(msg):
    print(f"[{fmt(elapsed())}] {msg}", flush=True)

def webhook(text):
    if not WEBHOOK_URL:
        return
    data = json.dumps({"text": text}).encode("utf-8")
    req = urllib.request.Request(
        WEBHOOK_URL,
        data=data,
        headers={"Content-Type": "application/json; charset=UTF-8"},
    )
    try:
        urllib.request.urlopen(req)
    except Exception as e:
        log(f"Webhook erreur: {e}")

def ssh_conn():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, username=USER, password=PASS, timeout=15)
    return ssh

def ssh_run(cmd, timeout=900, label=""):
    ssh = ssh_conn()
    log(label)
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    try:
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        code = stdout.channel.recv_exit_status()
    except Exception as e:
        print(f"  [WARN] ssh_run timeout/erreur ({label}): {e}", flush=True)
        try: ssh.close()
        except: pass
        return "", str(e), 1
    ssh.close()
    if out:
        for line in out.strip().split("\n")[-40:]:
            print(f"  {line}", flush=True)
    if err and code != 0:
        for line in err.strip().split("\n")[-10:]:
            print(f"  [ERR] {line}", flush=True)
    return out, err, code

def ssh_must(cmd, timeout=900, label=""):
    out, err, code = ssh_run(cmd, timeout, label)
    if code != 0:
        log(f"ECHEC: {label}")
        webhook(f"*ECHEC* etape: {label}\n```\n{err[:500]}\n```")
        sys.exit(1)
    return out

def terraform(args, cwd):
    log(f"Terraform: {args}")
    proc = subprocess.Popen(
        f"terraform {args}", cwd=cwd, shell=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace"
    )
    lines = []
    try:
        for line in proc.stdout:
            line = line.rstrip()
            lines.append(line)
            print(f"  {line}", flush=True)
        proc.wait(timeout=1800)
    except subprocess.TimeoutExpired:
        proc.kill()
        print("  [ERR] terraform timeout apres 30min", flush=True)
        return 1
    return proc.returncode


def kill_local_terraform():
    import subprocess as _sp
    _sp.run(["taskkill", "/F", "/IM", "terraform.exe"], capture_output=True)


def remove_local_tf_artifacts(tf_dir):
    """
    Efface le state Terraform local avant un apply from scratch.
    Sous Windows, terraform.exe ou l'IDE peut verrouiller terraform.tfstate : taskkill + retries.
    """
    names = [
        "terraform.tfstate",
        "terraform.tfstate.backup",
        ".terraform.tfstate.lock.info",
        # Ne jamais supprimer .terraform.lock.hcl : le retry apply sans init provoquerait une erreur.
    ]
    kill_local_terraform()
    time.sleep(2)
    for name in names:
        p = os.path.join(tf_dir, name)
        if not os.path.exists(p):
            continue
        ok = False
        for attempt in range(90):
            try:
                os.remove(p)
                ok = True
                break
            except PermissionError:
                if attempt % 10 == 0:
                    kill_local_terraform()
                    time.sleep(2)
                else:
                    time.sleep(1)
        if not ok:
            log(f"ECHEC: impossible de supprimer {p} (fichier verrouille — fermer Terraform/Cursor)")
            webhook(f"*ECHEC* Verrou Terraform Windows sur `{name}` — arreter terraform.exe puis relancer deploy-all")
            sys.exit(1)


tf_dir = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "terraform"))

# =====================================================================
log("=" * 60)
log("MSPR COGIP - DEPLOIEMENT COMPLET DEPUIS ZERO")
log("=" * 60)
if FROM_STEP > 1:
    webhook(f"*MSPR COGIP* - Deploiement reprise depuis etape *{FROM_STEP}* (MSPR_FROM_STEP)...")
else:
    webhook("*MSPR COGIP* - Deploiement complet lance depuis zero...")

# =========================== ETAPE 1 ================================
t = time.time()
if FROM_STEP > 1:
    log(f"[SKIP] Etape 1 reset Proxmox (MSPR_FROM_STEP={FROM_STEP})")
    step_times["1_reset"] = 0
else:
    webhook("*[1/7]* Reset Proxmox...")

    ssh_must(f"""
for vmid in 200 201 202 203 9002; do
    qm stop $vmid --timeout 15 2>/dev/null || true
    sleep 1
    qm destroy $vmid --purge 2>/dev/null && echo "VM $vmid detruite" || echo "VM $vmid: absente"
done
echo "Template VM {PACKER_TEMPLATE_VMID}: conserve au reset (non detruit). MSPR_FORCE_PACKER=1 pour forcer rebuild ISO/Packer."

iptables -t nat -F PREROUTING 2>/dev/null || true
echo 1 > /proc/sys/net/ipv4/ip_forward
iptables -t nat -C POSTROUTING -s 10.10.10.0/24 -o vmbr0 -j MASQUERADE 2>/dev/null || \
    iptables -t nat -A POSTROUTING -s 10.10.10.0/24 -o vmbr0 -j MASQUERADE

rm -f /var/lock/pve-manager/pve-storage-*
rm -rf /root/mspr-cogip-k8s
rm -f /root/.ssh/known_hosts
echo "RESET_OK"
""", label="[1/7] RESET PROXMOX")
    step_times["1_reset"] = time.time() - t
    webhook(f"*[1/7]* Reset OK ({fmt(step_times['1_reset'])})")

# =========================== ETAPE 2 ================================
t = time.time()
if FROM_STEP > 2:
    log(f"[SKIP] Etape 2 Packer (MSPR_FROM_STEP={FROM_STEP})")
    step_times["2_template"] = 0
else:
    run_packer = True
    if not FORCE_PACKER:
        probe_out, _, probe_code = ssh_run(
            f"""
set -e
TID={PACKER_TEMPLATE_VMID}
if qm config "$TID" >/dev/null 2>&1; then
  if qm config "$TID" | grep -qE '^template:[[:space:]]*(1|yes|true)'; then
    echo "TEMPLATE_REUSE_OK vmid=$TID"
    exit 0
  fi
  echo "VM $TID existe mais n'est pas un template (template:1) — lancement Packer"
  exit 1
fi
exit 1
""",
            timeout=120,
            label="[2/7] Verification template Packer (reuse auto si OK)",
        )
        if probe_code == 0 and "TEMPLATE_REUSE_OK" in probe_out:
            run_packer = False
            step_times["2_template"] = 0
            log(
                f"[SKIP] Etape 2 Packer — template {PACKER_TEMPLATE_VMID} deja sur Proxmox "
                "(MSPR_FORCE_PACKER=1 pour forcer rebuild ISO)"
            )
            webhook(
                f"*[2/7]* Packer *saute* — template *{PACKER_TEMPLATE_VMID}* reutilise (pas de rebuild ISO)"
            )

    if run_packer:
        if not MSPR_GIT_URL:
            log("ERREUR: definissez MSPR_GIT_URL (URL git de ce depot) pour l'etape Packer sur Proxmox.")
            sys.exit(1)
        webhook("*[2/7]* Template Proxmox via Packer (ISO autoinstall)...")

        ssh_must(
    rf"""
set -e
killall -9 packer 2>/dev/null || true

# Packer binaire (si absent sur le nœud)
if ! command -v packer >/dev/null 2>&1; then
  PACKER_VER=1.11.2
  wget -qO /tmp/packer.zip "https://releases.hashicorp.com/packer/${{PACKER_VER}}/packer_${{PACKER_VER}}_linux_amd64.zip"
  unzip -oq /tmp/packer.zip -d /usr/local/bin
  chmod +x /usr/local/bin/packer
fi
packer version | head -1

# ISO live server attendu par packer/variables.pkr.hcl (local:iso/...)
ISO_PATH="/var/lib/vz/template/iso/ubuntu-22.04.5-live-server-amd64.iso"
mkdir -p /var/lib/vz/template/iso
if [ ! -f "$ISO_PATH" ]; then
  echo "[Packer] Telechargement ISO Ubuntu 22.04.5 live-server (peut prendre plusieurs minutes)..."
  wget -O "$ISO_PATH" "https://releases.ubuntu.com/22.04/ubuntu-22.04.5-live-server-amd64.iso"
fi

# Depôt MSPR (étape 1 a supprime /root/mspr-cogip-k8s)
cd /root
rm -rf mspr-cogip-k8s
git clone --depth 1 -b main "{MSPR_GIT_URL}" mspr-cogip-k8s
cd mspr-cogip-k8s
HASH=$(openssl passwd -6 ubuntu)
sed -i "s|__UBUNTU_HASH__|${{HASH}}|" packer/http/user-data

TEMPLATE_ID={PACKER_TEMPLATE_VMID}
if qm config "$TEMPLATE_ID" >/dev/null 2>&1; then
  qm stop "$TEMPLATE_ID" --timeout 45 2>/dev/null || true
  sleep 3
  for n in 1 2 3 4 5 6; do
    qm destroy "$TEMPLATE_ID" --purge 2>/dev/null && break
    qm stop "$TEMPLATE_ID" --timeout 30 2>/dev/null || true
    sleep 2
  done
  if qm config "$TEMPLATE_ID" >/dev/null 2>&1; then
    echo "ERREUR: VM $TEMPLATE_ID toujours presente apres destroy"
    exit 1
  fi
fi

cd packer
packer init .
export PACKER_LOG=1
export PACKER_LOG_PATH=/tmp/packer-mspr-deploy.log
rm -f /tmp/packer-tee-mspr-deploy.log
set +e
set -o pipefail
packer build \
  -var 'proxmox_password={PASS}' \
  -var 'proxmox_node={PROXMOX_NODE}' \
  -var 'vm_id={PACKER_TEMPLATE_VMID}' \
  . 2>&1 | tee /tmp/packer-tee-mspr-deploy.log
RC=${{PIPESTATUS[0]}}
set -e
if [ "$RC" -ne 0 ]; then exit "$RC"; fi

# Le plugin Proxmox convertit la VM en template (vm_id = Terraform clone source)
qm list | grep "$TEMPLATE_ID" || true
echo "PACKER_TEMPLATE_OK"
""",
            timeout=10800,
            label="[2/7] PACKER template (ISO autoinstall)",
        )
        step_times["2_template"] = time.time() - t
        webhook(f"*[2/7]* Packer template OK ({fmt(step_times['2_template'])})")

# =========================== ETAPE 3 ================================
t = time.time()
if FROM_STEP > 3:
    log(f"[SKIP] Etape 3 Terraform (MSPR_FROM_STEP={FROM_STEP})")
    step_times["3_terraform"] = 0
else:
    webhook("*[3/7]* Terraform apply...")

    remove_local_tf_artifacts(tf_dir)

    rc = terraform("init -upgrade -input=false", tf_dir)
    if rc != 0:
        webhook("*ECHEC* Terraform init")
        sys.exit(1)

    rc = terraform("apply -auto-approve -parallelism=1 -input=false", tf_dir)
    if rc != 0:
        log("Terraform echoue, nettoyage et retry...")
        kill_local_terraform()
        time.sleep(3)
        ssh_run("""
        for vmid in 200 201 202 203; do
            qm stop $vmid --timeout 10 2>/dev/null || true
            qm destroy $vmid --purge 2>/dev/null || true
        done
        rm -f /var/lock/pve-manager/pve-storage-*
        """, label="Cleanup VMs")
        remove_local_tf_artifacts(tf_dir)
        time.sleep(10)
        rc = terraform("init -upgrade -input=false", tf_dir)
        if rc != 0:
            webhook("*ECHEC* Terraform init (retry)")
            sys.exit(1)
        rc = terraform("apply -auto-approve -parallelism=1 -input=false", tf_dir)
        if rc != 0:
            webhook("*ECHEC* Terraform apply x2")
            sys.exit(1)

    step_times["3_terraform"] = time.time() - t
    webhook(f"*[3/7]* Terraform OK ({fmt(step_times['3_terraform'])})")

if FROM_STEP <= 3:
    webhook("*Post-Terraform* Demarrage VMs echelonne (limiter IO disque / io-error)...")
    ssh_must(PROXMOX_STAGGER_START.strip(), label="Post-terraform: demarrage echelonne VMs")

# =========================== ETAPE 4 ================================
t = time.time()
if FROM_STEP <= 4:
    webhook("*[4/7]* Setup Ansible + prep VMs...")
    if not MSPR_GIT_URL:
        log("ERREUR: definissez MSPR_GIT_URL pour cloner le depot sur Proxmox.")
        sys.exit(1)

    ssh_must(
        f"""
apt-get update -qq > /dev/null 2>&1
apt-get install -y -qq ansible python3-pip git screen > /dev/null 2>&1
pip3 install --break-system-packages kubernetes PyYAML jsonpatch 2>&1 | tail -1
echo "Ansible: $(ansible --version | head -1)"

cd /root
rm -rf mspr-cogip-k8s
git clone --depth 1 -b main "{MSPR_GIT_URL}" mspr-cogip-k8s 2>&1 | tail -2
"""
        + PATCH_REPO_NFS_APT_PINS
        + """
rm -f /root/.ssh/id_ansible /root/.ssh/id_ansible.pub
ssh-keygen -t ed25519 -f /root/.ssh/id_ansible -N '' -q
echo "SSH key OK"
""", label="[4/7] Install Ansible + clone")

    log("Attente boot VMs (120s - cloud-init + RNG)...")
    time.sleep(120)

    ssh_must("""
PROXKEY=$(cat /root/.ssh/id_ansible.pub)
USERKEY="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIHcjlUzYzCiRGTe+TWekFc/RmLX13pcXijChNYZOiBBw mspr-cogip"
TMPFILE=$(mktemp)
echo "$USERKEY" > $TMPFILE
echo "$PROXKEY" >> $TMPFILE
for vmid in 200 201 202 203; do
    qm set $vmid --sshkeys $TMPFILE 2>&1 | grep -v sshkeys || true
    qm cloudinit update $vmid 2>/dev/null
done
rm -f $TMPFILE

for vmid in 200 201 202 203; do
    qm reboot $vmid 2>/dev/null && echo "VM $vmid: reboot OK" && continue
    echo "VM $vmid: reboot echoue, tentative reset..."
    qm reset $vmid 2>/dev/null && echo "VM $vmid: reset OK" && continue
    echo "VM $vmid: reset echoue, stop+start..."
    qm stop $vmid --timeout 30 2>/dev/null; sleep 3; qm start $vmid 2>/dev/null
    echo "VM $vmid: start OK"
done
echo "SSH keys injected, VMs rebooting"
""", label="Inject SSH keys + reboot VMs")

    log("Attente reboot (150s - cloud-init second boot)...")
    time.sleep(150)

    ssh_must(
        PROXMOX_SSH_PROBE_ALL.strip(),
        timeout=7200,
        label="Test SSH toutes VMs",
    )

    log("Fix dpkg + install paquets sur toutes les VMs...")
    ssh_must("""
for ip in 10.10.10.10 10.10.10.11 10.10.10.12 10.10.10.13; do
    echo "--- $ip ---"
    ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 -i /root/.ssh/id_ansible ubuntu@$ip \
        'sudo dpkg --configure -a 2>&1; sudo apt --fix-broken install -y 2>&1; sudo apt-get update -qq 2>&1' | tail -3
    echo "$ip: OK"
done
echo "DPKG_DONE"
""", timeout=600, label="Fix dpkg toutes VMs")

    log("Pause 30s apres dpkg (evite coupure reseau temporaire post-apt)...")
    time.sleep(30)

    log("Install kubernetes Python sur CP (avec retry)...")
    ssh_must("""
for attempt in 1 2 3; do
  echo "Tentative $attempt..."
  OK=false
  for w in $(seq 1 12); do
    if ssh -o StrictHostKeyChecking=no -o ConnectTimeout=8 -i /root/.ssh/id_ansible ubuntu@10.10.10.10 \
      'sudo apt-get update -qq 2>&1 | tail -1 && sudo apt-get install -y python3-kubernetes python3-pip python3-yaml python3-jsonpatch 2>&1 | tail -3 && python3 -c "import kubernetes; print(kubernetes.__version__)" && echo K8S_PY_OK' 2>&1; then
      OK=true; break
    fi
    echo "CP pas pret ($w/12), attente 10s..."
    sleep 10
  done
  [ "$OK" = "true" ] && break
  [ "$attempt" -lt 3 ] && echo "Retry dans 20s..." && sleep 20
done
if [ "$OK" = "false" ]; then echo "ECHEC K8S_PY apres 3 tentatives"; exit 1; fi
echo "K8S_PY_DONE"
""", timeout=600, label="Install kubernetes lib CP")

    ssh_must("""
cd /root/mspr-cogip-k8s/ansible
mkdir -p inventory
cat > inventory/hosts.yml << 'INV'
---
all:
  vars:
    ansible_user: ubuntu
    ansible_ssh_private_key_file: /root/.ssh/id_ansible
    ansible_python_interpreter: /usr/bin/python3
    k3s_version: "v1.29.2+k3s1"
    odoo_domain: "odoo.local"
  children:
    k3s_server:
      hosts:
        k3s-control-plane:
          ansible_host: 10.10.10.10
          k3s_role: server
    k3s_agents:
      hosts:
        k3s-worker-1:
          ansible_host: 10.10.10.11
          k3s_role: agent
        k3s-worker-2:
          ansible_host: 10.10.10.12
          k3s_role: agent
    nfs:
      hosts:
        nfs-server:
          ansible_host: 10.10.10.13
          nfs_export_path: /srv/nfs/k8s
    k3s_cluster:
      children:
        k3s_server:
        k3s_agents:
INV
ln -sf ../group_vars inventory/group_vars 2>/dev/null || true
ln -sf ../group_vars playbooks/group_vars 2>/dev/null || true
sed -i 's/stdout_callback = yaml/stdout_callback = default/' ansible.cfg 2>/dev/null || true
ansible-galaxy collection install -r requirements.yml --force 2>&1 | tail -3
echo "SETUP_OK"
""", label="Config inventaire + Galaxy")

    step_times["4_setup"] = time.time() - t
    webhook(f"*[4/7]* Setup OK ({fmt(step_times['4_setup'])})")

elif FROM_STEP == 5:
    # Reprise apres echec Ansible : ne pas detruire l'infra, relancer VM(s) puis prep + playbook
    webhook("*[4/7]* Reprise prep Ansible (MSPR_FROM_STEP=5)...")
    if not MSPR_GIT_URL:
        log("ERREUR: definissez MSPR_GIT_URL pour la reprise Ansible sur Proxmox.")
        sys.exit(1)
    log(f"MSPR_RESTART_VMS={RESTART_VMS or '(aucun — definir ex. 202 pour k3s-worker-2)'}")

    ssh_run(PROXMOX_IO_RECOVER.strip(), label="[reprise] Scan io-error Proxmox (qm status)")

    _vm_tokens = [x for x in re.split(r"[\s,]+", RESTART_VMS) if x.isdigit()]
    if _vm_tokens:
        _ids = " ".join(_vm_tokens)
        ssh_must(f"""
for vmid in {_ids}; do
    qm reboot $vmid 2>/dev/null && echo "VM $vmid reboot OK" && continue
    qm reset $vmid 2>/dev/null && echo "VM $vmid reset OK" && continue
    qm stop $vmid --timeout 45 2>/dev/null; sleep 3; qm start $vmid && echo "VM $vmid start OK"
done
""", label="Redemarrage VM(s) Proxmox (reprise)")
        log("Attente 120s apres redemarrage VM (boot + cloud-init)...")
        time.sleep(120)

    ssh_must(
        f"""
apt-get update -qq > /dev/null 2>&1
apt-get install -y -qq ansible python3-pip git screen > /dev/null 2>&1
pip3 install --break-system-packages kubernetes PyYAML jsonpatch 2>&1 | tail -1
if [ ! -d /root/mspr-cogip-k8s/.git ]; then
  cd /root && rm -rf mspr-cogip-k8s && git clone --depth 1 -b main "{MSPR_GIT_URL}" mspr-cogip-k8s
else
  cd /root/mspr-cogip-k8s && git pull --ff-only 2>&1 | tail -5 || true
fi
if [ ! -f /root/.ssh/id_ansible ]; then
  rm -f /root/.ssh/id_ansible /root/.ssh/id_ansible.pub
  ssh-keygen -t ed25519 -f /root/.ssh/id_ansible -N '' -q
  PROXKEY=$(cat /root/.ssh/id_ansible.pub)
  USERKEY="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIHcjlUzYzCiRGTe+TWekFc/RmLX13pcXijChNYZOiBBw mspr-cogip"
  TMPFILE=$(mktemp)
  echo "$USERKEY" > $TMPFILE
  echo "$PROXKEY" >> $TMPFILE
  for vmid in 200 201 202 203; do
    qm set $vmid --sshkeys $TMPFILE 2>&1 | grep -v sshkeys || true
    qm cloudinit update $vmid 2>/dev/null
  done
  rm -f $TMPFILE
fi
echo "REPRISE_PREP_OK"
""", label="[reprise] Ansible + depot + cle SSH si besoin")

    ssh_must(PATCH_REPO_NFS_APT_PINS.strip(), label="[reprise] Patch NFS apt + main.yml role (depot local)")

    ssh_must(
        PROXMOX_SSH_PROBE_ALL.strip(),
        timeout=7200,
        label="[reprise] Test SSH toutes VMs",
    )

    ssh_must("""
for ip in 10.10.10.10 10.10.10.11 10.10.10.12 10.10.10.13; do
    echo "--- $ip ---"
    ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 -i /root/.ssh/id_ansible ubuntu@$ip \
        'sudo dpkg --configure -a 2>&1; sudo apt --fix-broken install -y 2>&1; sudo apt-get update -qq 2>&1' | tail -3
    echo "$ip: OK"
done
echo "DPKG_DONE"
""", timeout=600, label="[reprise] Fix dpkg toutes VMs")

    log("Pause 30s apres dpkg...")
    time.sleep(30)

    ssh_must("""
for attempt in 1 2 3; do
  echo "Tentative $attempt..."
  OK=false
  for w in $(seq 1 12); do
    if ssh -o StrictHostKeyChecking=no -o ConnectTimeout=8 -i /root/.ssh/id_ansible ubuntu@10.10.10.10 \
      'sudo apt-get update -qq 2>&1 | tail -1 && sudo apt-get install -y python3-kubernetes python3-pip python3-yaml python3-jsonpatch 2>&1 | tail -3 && python3 -c "import kubernetes; print(kubernetes.__version__)" && echo K8S_PY_OK' 2>&1; then
      OK=true; break
    fi
    echo "CP pas pret ($w/12), attente 10s..."
    sleep 10
  done
  [ "$OK" = "true" ] && break
  [ "$attempt" -lt 3 ] && echo "Retry dans 20s..." && sleep 20
done
if [ "$OK" = "false" ]; then echo "ECHEC K8S_PY apres 3 tentatives"; exit 1; fi
echo "K8S_PY_DONE"
""", timeout=600, label="[reprise] Install kubernetes lib CP")

    ssh_must("""
cd /root/mspr-cogip-k8s/ansible
mkdir -p inventory
cat > inventory/hosts.yml << 'INV'
---
all:
  vars:
    ansible_user: ubuntu
    ansible_ssh_private_key_file: /root/.ssh/id_ansible
    ansible_python_interpreter: /usr/bin/python3
    k3s_version: "v1.29.2+k3s1"
    odoo_domain: "odoo.local"
  children:
    k3s_server:
      hosts:
        k3s-control-plane:
          ansible_host: 10.10.10.10
          k3s_role: server
    k3s_agents:
      hosts:
        k3s-worker-1:
          ansible_host: 10.10.10.11
          k3s_role: agent
        k3s-worker-2:
          ansible_host: 10.10.10.12
          k3s_role: agent
    nfs:
      hosts:
        nfs-server:
          ansible_host: 10.10.10.13
          nfs_export_path: /srv/nfs/k8s
    k3s_cluster:
      children:
        k3s_server:
        k3s_agents:
INV
ln -sf ../group_vars inventory/group_vars 2>/dev/null || true
ln -sf ../group_vars playbooks/group_vars 2>/dev/null || true
sed -i 's/stdout_callback = yaml/stdout_callback = default/' ansible.cfg 2>/dev/null || true
ansible-galaxy collection install -r requirements.yml --force 2>&1 | tail -3
echo "SETUP_OK"
""", label="[reprise] Config inventaire + Galaxy")

    step_times["4_setup"] = time.time() - t
    webhook(f"*[4/7]* Prep reprise OK ({fmt(step_times['4_setup'])})")

else:
    log(f"[SKIP] Etape 4 setup complet (MSPR_FROM_STEP={FROM_STEP})")
    step_times["4_setup"] = 0

# =========================== ETAPE 5 ================================
t = time.time()
if FROM_STEP <= 5:
    webhook("*[5/7]* Ansible playbook (K3s + NFS + Odoo)...")

    max_wait = 7200
    poll = 30
    ansible_ok = False
    for attempt in (1, 2):
        ssh_run("""
cd /root/mspr-cogip-k8s/ansible
screen -S ansible -X quit 2>/dev/null || true
rm -f /tmp/ansible-deploy.log /tmp/ansible-exit-code
screen -dmS ansible bash -c 'ansible-playbook playbooks/site.yml -v > /tmp/ansible-deploy.log 2>&1; echo $? > /tmp/ansible-exit-code'
echo "Ansible started"
""", label=f"[5/7] Launch Ansible{' (tentative 2)' if attempt == 2 else ''}")

        waited = 0
        code = None
        while waited < max_wait:
            time.sleep(poll)
            waited += poll
            out, _, _ = ssh_run("""
    if [ -f /tmp/ansible-exit-code ]; then
        CODE=$(cat /tmp/ansible-exit-code)
        echo "FINISHED:$CODE"
        tail -15 /tmp/ansible-deploy.log
    else
        echo "RUNNING"
        tail -3 /tmp/ansible-deploy.log 2>/dev/null || echo "(vide)"
    fi
    """, label=f"Poll ({fmt(waited)})")

            if "FINISHED:" in out:
                code = out.split("FINISHED:")[1].split("\n")[0].strip()
                break

        if code is None:
            webhook("*ECHEC* Ansible timeout 30min")
            sys.exit(1)

        if code == "0":
            log("Ansible OK!")
            ansible_ok = True
            break

        if code == "2":
            recap_out, _, _ = ssh_run(
                "grep -A 20 'PLAY RECAP' /tmp/ansible-deploy.log | tail -20",
                label="PLAY RECAP"
            )
            failed_counts = re.findall(r'failed=(\d+)', recap_out)
            total_failed = sum(int(x) for x in failed_counts)
            if total_failed == 0:
                log("Ansible code 2 / 0 failed, OK")
                ansible_ok = True
                break
            if total_failed <= 1 and "Health check" in (ssh_run("grep -i 'health' /tmp/ansible-deploy.log | tail -3")[0]):
                log("Ansible code 2 / health check fail only, continuing")
                ansible_ok = True
                break
            log(f"Ansible FAILED: {total_failed} tasks failed")
            ssh_run("tail -60 /tmp/ansible-deploy.log", label="Error log")
            webhook(f"*ECHEC* Ansible - {total_failed} failed")
            sys.exit(1)

        if code == "4" and attempt == 1:
            log("Ansible code 4 (hotes injoignables) — recuperation IO Proxmox + 2e tentative")
            webhook("*Ansible* code 4 — retry apres demarrage echelonne VMs")
            ssh_must(PROXMOX_STAGGER_START.strip(), label="Recovery: demarrage echelonne VMs")
            time.sleep(120)
            continue

        log(f"Ansible FAILED (code {code})")
        ssh_run("tail -50 /tmp/ansible-deploy.log", label="Error log")
        webhook(f"*ECHEC* Ansible (code {code})")
        sys.exit(1)

    if not ansible_ok:
        webhook("*ECHEC* Ansible sans succes apres retry")
        sys.exit(1)

    step_times["5_ansible"] = time.time() - t
    webhook(f"*[5/7]* Ansible OK ({fmt(step_times['5_ansible'])})")
else:
    log(f"[SKIP] Etape 5 Ansible (MSPR_FROM_STEP={FROM_STEP})")
    step_times["5_ansible"] = 0

# =========================== ETAPE 6 ================================
t = time.time()
if FROM_STEP <= 6:
    webhook("*[6/7]* Init Odoo + NAT...")

    ssh_must("""
ssh -o StrictHostKeyChecking=no -i /root/.ssh/id_ansible ubuntu@10.10.10.10 bash << 'REMOTE'
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
set -e
echo "=== Attente pods Odoo (Helm Bitnami) ==="
for i in $(seq 1 60); do
  if kubectl get pods -n odoo -l app.kubernetes.io/name=odoo --no-headers 2>/dev/null | grep -q Running; then
    echo "Pod Odoo Running"
    break
  fi
  echo "  attente ($i/60)..."
  sleep 15
done
kubectl get pods -n odoo -o wide
kubectl get ingress -n odoo -o wide || true
echo "INIT_ODOO_OK"
REMOTE
""", timeout=900, label="[6/7] Verification pods Odoo (Bitnami) + NAT")

    ssh_must("""
CP="10.10.10.10"
iptables -t nat -C PREROUTING -i vmbr0 -p tcp --dport 80 -j DNAT --to-destination ${CP}:80 2>/dev/null || \
    iptables -t nat -A PREROUTING -i vmbr0 -p tcp --dport 80 -j DNAT --to-destination ${CP}:80
iptables -t nat -C PREROUTING -i vmbr0 -p tcp --dport 443 -j DNAT --to-destination ${CP}:443 2>/dev/null || \
    iptables -t nat -A PREROUTING -i vmbr0 -p tcp --dport 443 -j DNAT --to-destination ${CP}:443
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq iptables-persistent > /dev/null 2>&1
netfilter-persistent save > /dev/null 2>&1
echo "NAT OK: 80+443 -> $CP"
""", label="NAT iptables")

    step_times["6_init"] = time.time() - t
    webhook(f"*[6/7]* Init OK ({fmt(step_times['6_init'])})")
else:
    log(f"[SKIP] Etape 6 Init Odoo + NAT (MSPR_FROM_STEP={FROM_STEP})")
    step_times["6_init"] = 0

# =========================== ETAPE 7 ================================
t = time.time()
odoo_ok = False
if FROM_STEP <= 7:
    webhook("*[7/7]* Verification finale...")

    log("Attente 45s pour Odoo restart complet...")
    time.sleep(45)

    out, _, _ = ssh_run("""
for i in $(seq 1 20); do
    CODE=$(curl -sk -o /dev/null -w '%{http_code}' -H 'Host: odoo.local' https://10.10.10.10:443/ --max-time 15)
    echo "Tentative $i: HTTPS $CODE"
    if [ "$CODE" = "200" ] || [ "$CODE" = "302" ] || [ "$CODE" = "303" ]; then
        echo "ODOO_OK"
        exit 0
    fi
    sleep 15
done
echo "ODOO_FAIL"
exit 1
""", label="[7/7] Verify Odoo HTTPS (certificat autosigne)")

    odoo_ok = "ODOO_OK" in out
    step_times["7_verify"] = time.time() - t
else:
    log(f"[SKIP] Etape 7 verification (MSPR_FROM_STEP={FROM_STEP})")
    step_times["7_verify"] = 0

TOTAL = time.time() - TOTAL_START

print(f"\n{'=' * 60}", flush=True)
print("RECAPITULATIF", flush=True)
print(f"{'=' * 60}", flush=True)
for key, label in [
    ("1_reset", "Reset Proxmox"),
    ("2_template", "Template VM"),
    ("3_terraform", "Terraform"),
    ("4_setup", "Setup Ansible"),
    ("5_ansible", "Ansible playbook"),
    ("6_init", "Init Odoo + NAT"),
    ("7_verify", "Verification"),
]:
    print(f"  {label:25s}: {fmt(step_times.get(key, 0))}", flush=True)
print(f"  {'─' * 40}", flush=True)
print(f"  {'TOTAL':25s}: {fmt(TOTAL)}", flush=True)
print(f"  Odoo: {'OK' if odoo_ok else 'FAIL'}", flush=True)
print(f"{'=' * 60}", flush=True)

if odoo_ok:
    msg = f"""*MSPR COGIP - Deploiement termine avec succes !*

Temps total : *{fmt(TOTAL)}*

- Reset Proxmox : {fmt(step_times.get('1_reset', 0))}
- Template VM : {fmt(step_times.get('2_template', 0))}
- Terraform : {fmt(step_times.get('3_terraform', 0))}
- Setup Ansible : {fmt(step_times.get('4_setup', 0))}
- Ansible (K3s+Odoo) : {fmt(step_times.get('5_ansible', 0))}
- Init Odoo + NAT : {fmt(step_times.get('6_init', 0))}
- Verification : {fmt(step_times.get('7_verify', 0))}

Odoo: https://odoo.local (TLS autosigne — accepter l'avertissement navigateur ; identifiants = variables Ansible / vault)"""
else:
    msg = f"*MSPR* - Deploy {fmt(TOTAL)} mais Odoo inaccessible. Check manuel requis."

webhook(msg)
log("DEPLOIEMENT TERMINE!")
