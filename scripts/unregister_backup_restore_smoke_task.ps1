[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
schtasks.exe /Delete /TN "SMAI-Backup-Restore-Smoke" /F | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Could not remove SMAI-Backup-Restore-Smoke."
}
Write-Host "[OK] Removed: SMAI-Backup-Restore-Smoke"
