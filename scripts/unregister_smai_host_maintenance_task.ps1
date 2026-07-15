[CmdletBinding()]
param(
    [switch]$RestoreLegacyWeeklyRestart
)

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Changing SMAI-Host-Maintenance or WeeklyRestart requires an elevated PowerShell session. No task was changed."
}

$taskName = "SMAI-Host-Maintenance"
$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($null -ne $task) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host "[OK] Unregistered: $taskName"
}
if ($RestoreLegacyWeeklyRestart) {
    Enable-ScheduledTask -TaskName "WeeklyRestart" -ErrorAction Stop | Out-Null
    Write-Host "[OK] Re-enabled legacy task: WeeklyRestart"
}
