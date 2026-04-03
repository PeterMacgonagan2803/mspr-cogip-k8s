# Preparation SSH depuis ton PC vers Proxmox (une seule fois, mot de passe demande au besoin).
# Ensuite : ssh proxmox-mspr "qm list" fonctionne sans mot de passe pour les scripts / Cursor.

$ErrorActionPreference = "Stop"
$sshDir = Join-Path $env:USERPROFILE ".ssh"
$key = Join-Path $sshDir "id_ed25519_mspr"
$hostBlock = @"

Host proxmox-mspr
  HostName VOTRE_IP_PROXMOX
  User root
  IdentityFile $key
  StrictHostKeyChecking accept-new
"@

New-Item -ItemType Directory -Force -Path $sshDir | Out-Null

if (-not (Test-Path $key)) {
    ssh-keygen -t ed25519 -f $key -N '""' -C "mspr-$(whoami)-$(hostname)"
    Write-Host "Cle creee: $key"
}

$configPath = Join-Path $sshDir "config"
$needHost = $true
if (Test-Path $configPath) {
    $c = Get-Content $configPath -Raw
    if ($c -match "Host proxmox-mspr") { $needHost = $false }
}
if ($needHost) {
    Add-Content -Path $configPath -Value "`n$hostBlock`n"
    Write-Host "Bloc Host proxmox-mspr ajoute a $configPath"
} else {
    Write-Host "proxmox-mspr deja present dans $configPath"
}

Write-Host ""
Write-Host "Etape suivante (tu colles le mot de passe root une fois) :"
Write-Host "  type `"$key.pub`" | ssh root@VOTRE_IP_PROXMOX `"mkdir -p .ssh && chmod 700 .ssh && cat >> .ssh/authorized_keys && chmod 600 .ssh/authorized_keys`""
Write-Host ""
Write-Host "Test sans mot de passe :"
Write-Host "  ssh proxmox-mspr `"hostname`""
