#Requires -Version 5.1
<#
.SYNOPSIS
    MSPR TPRE961 -- COGIP -- Reprise apres echec Ansible (sans reset / Packer / Terraform).

.DESCRIPTION
    Definit MSPR_FROM_STEP=5 puis lance deploy-all.py : preparation minimale, playbook,
    init Odoo, verification. Le cluster et les VMs doivent deja exister sur Proxmox.

.NOTES
    Optionnel : $env:MSPR_RESTART_VMS = "202" avant execution pour forcer reboot d'une VM.
#>
$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot

$env:MSPR_FROM_STEP = "5"
Remove-Item Env:MSPR_FORCE_PACKER -ErrorAction SilentlyContinue
# MSPR_RESTART_VMS conserve si defini avant l'appel (ex. "202" pour worker-2)

python deploy-all.py
