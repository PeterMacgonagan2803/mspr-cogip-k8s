"""Execute un script shell sur Proxmox (root) en l'envoyant sur stdin (bash -s)."""
import os
import pathlib
import sys

import paramiko

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: run_proxmox_script.py <script.sh>", file=sys.stderr)
        return 2
    host = os.environ.get("MSPR_PROXMOX_HOST", "").strip()
    password = os.environ.get("MSPR_PROXMOX_PASS", "").strip()
    user = os.environ.get("MSPR_PROXMOX_USER", "root").strip()
    timeout = int(os.environ.get("MSPR_SSH_TIMEOUT", "3600"))
    if not host or not password:
        print("MSPR_PROXMOX_HOST et MSPR_PROXMOX_PASS requis", file=sys.stderr)
        return 2
    body = pathlib.Path(sys.argv[1]).read_bytes().replace(b"\r\n", b"\n")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username=user, password=password, timeout=20)
    stdin, stdout, stderr = ssh.exec_command("bash -s", timeout=timeout)
    stdin.write(body.decode())
    stdin.channel.shutdown_write()
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
