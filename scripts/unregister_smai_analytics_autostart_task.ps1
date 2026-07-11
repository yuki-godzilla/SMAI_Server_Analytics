[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$taskName = "SMAI-Server-Analytics"
$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($null -ne $task) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host "[OK] Unregistered: $taskName"
} else {
    Write-Host "[SMAI] Task is not registered: $taskName"
}
