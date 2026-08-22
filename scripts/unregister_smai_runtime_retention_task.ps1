[CmdletBinding()]
param()

$taskName = "SMAI-Runtime-Retention"
if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host "[OK] Unregistered: $taskName"
} else {
    Write-Host "[SMAI] Task is not registered: $taskName"
}
