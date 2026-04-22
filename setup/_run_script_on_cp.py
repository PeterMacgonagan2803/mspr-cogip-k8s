"""Copie un .sh sur Proxmox puis scp+execute sur 10.10.10.10 (ubuntu)."""
import os
import pathlib
import sys
from io import BytesIO

import paramiko

PROX = os.environ.get("MSPR_PROXMOX_HOST", "").strip()
PWD = os.environ.get("MSPR_PROXMOX_PASS", "").strip()
USER = os.environ.get("MSPR_PROXMOX_USER", "root").strip()
CP = "10.10.10.10"
KEY = "/root/.ssh/id_ansible"


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: _run_script_on_cp.py <script.sh>", file=sys.stderr)
        return 2
    if not PROX or not PWD:
        print("MSPR_PROXMOX_HOST et MSPR_PROXMOX_PASS requis", file=sys.stderr)
        return 2
    src = pathlib.Path(sys.argv[1]).resolve()
    data = src.read_bytes().replace(b"\r\n", b"\n")
    remote = f"/tmp/{src.name}"
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(PROX, username=USER, password=PWD, timeout=20)
    sftp = ssh.open_sftp()
    sftp.putfo(BytesIO(data), remote)
    sftp.close()
    cmd = (
        f"chmod +x {remote} && "
        f"scp -o StrictHostKeyChecking=no -o BatchMode=yes -i {KEY} {remote} ubuntu@{CP}:{remote} && "
        f"ssh -o StrictHostKeyChecking=no -o BatchMode=yes -i {KEY} ubuntu@{CP} sudo bash {remote}"
    )
    _stdin, stdout, stderr = ssh.exec_command(cmd, timeout=300)
    out = stdout.read().decode()
    err = stderr.read().decode()
    code = stdout.channel.recv_exit_status()
    ssh.close()
    if out:
        print(out, end="")
    if err:
        print(err, end="", file=sys.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
