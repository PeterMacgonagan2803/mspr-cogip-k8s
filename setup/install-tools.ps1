# =============================================================================
# Installation des outils - MSPR COGIP
# Exécuter en tant qu'Administrateur PowerShell
# =============================================================================

Write-Host "=== Installation des outils MSPR COGIP ===" -ForegroundColor Cyan

# Terraform
Write-Host "`n[1/5] Installation de Terraform..." -ForegroundColor Yellow
winget install HashiCorp.Terraform --accept-source-agreements --accept-package-agreements

# Packer
Write-Host "`n[2/5] Installation de Packer..." -ForegroundColor Yellow
winget install HashiCorp.Packer --accept-source-agreements --accept-package-agreements

# Helm
Write-Host "`n[3/5] Installation de Helm..." -ForegroundColor Yellow
winget install Helm.Helm --accept-source-agreements --accept-package-agreements

# kubectl
Write-Host "`n[4/5] Installation de kubectl..." -ForegroundColor Yellow
winget install Kubernetes.kubectl --accept-source-agreements --accept-package-agreements

# Ansible (via pip, nécessite Python)
Write-Host "`n[5/5] Installation d'Ansible via pip..." -ForegroundColor Yellow
winget install Python.Python.3.11 --accept-source-agreements --accept-package-agreements
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
pip install ansible ansible-lint

# Rafraîchir le PATH
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")

Write-Host "`n=== Vérification des installations ===" -ForegroundColor Cyan

Write-Host "Terraform : " -NoNewline
try { terraform --version 2>$null } catch { Write-Host "NON INSTALLE" -ForegroundColor Red }

Write-Host "Packer    : " -NoNewline
try { packer --version 2>$null } catch { Write-Host "NON INSTALLE" -ForegroundColor Red }

Write-Host "Helm      : " -NoNewline
try { helm version --short 2>$null } catch { Write-Host "NON INSTALLE" -ForegroundColor Red }

Write-Host "kubectl   : " -NoNewline
try { kubectl version --client --short 2>$null } catch { Write-Host "NON INSTALLE" -ForegroundColor Red }

Write-Host "Ansible   : " -NoNewline
try { ansible --version 2>$null } catch { Write-Host "NON INSTALLE" -ForegroundColor Red }

Write-Host "`n=== Installation terminée ===" -ForegroundColor Green
Write-Host "Si certains outils ne sont pas detectes, fermez et rouvrez PowerShell pour rafraichir le PATH." -ForegroundColor Yellow
