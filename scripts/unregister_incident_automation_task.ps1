[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Unregister-ScheduledTask -TaskName "SMAI-Incident-Automation" -Confirm:$false -ErrorAction SilentlyContinue
Write-Host "[OK] Removed: SMAI-Incident-Automation"
