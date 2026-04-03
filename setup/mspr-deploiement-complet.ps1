#Requires -Version 5.1
<#
.SYNOPSIS
    MSPR TPRE961 -- COGIP -- Deploiement automatique complet (zero vers Odoo).

.DESCRIPTION
    Meme role que `python deploy-all.py` : arret des processus terraform.exe locaux
    (evite verrou terraform.tfstate sous Windows), puis orchestration SSH vers Proxmox.
    Voir setup/GUIDE-DEMARRAGE.md section "Alternative : Deploiement automatique complet".

.NOTES
    Prerequis : etapes 0-2 du guide (outils, reseau Proxmox), terraform.tfvars rempli.
#>
$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot

taskkill /F /IM terraform.exe 2>$null | Out-Null
Start-Sleep -Seconds 1
Remove-Item Env:MSPR_FROM_STEP, Env:MSPR_FORCE_PACKER, Env:MSPR_RESTART_VMS -ErrorAction SilentlyContinue

python deploy-all.py
