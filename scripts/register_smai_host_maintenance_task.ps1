[CmdletBinding()]
param(
    [switch]$ReplaceLegacyWeeklyRestart
)

$ErrorActionPreference = "Stop"
$taskName = "SMAI-Host-Maintenance"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$script = Join-Path $projectRoot "scripts\invoke_smai_host_maintenance.ps1"
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$currentPrincipal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Registering $taskName and replacing WeeklyRestart requires an elevated PowerShell session. No task was changed."
}

$legacyTask = Get-ScheduledTask -TaskName "WeeklyRestart" -ErrorAction SilentlyContinue
if ($null -ne $legacyTask -and $legacyTask.State -ne "Disabled" -and -not $ReplaceLegacyWeeklyRestart) {
    throw "WeeklyRestart is still enabled. Re-run with -ReplaceLegacyWeeklyRestart from an elevated PowerShell session to avoid two maintenance tasks running together."
}
$principal = New-ScheduledTaskPrincipal -UserId $identity.Name -LogonType S4U -RunLevel Highest
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At "04:00"
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -RestartCount 1 -RestartInterval (New-TimeSpan -Minutes 30) -ExecutionTimeLimit (New-TimeSpan -Minutes 20) -StartWhenAvailable
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument ('-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "{0}"' -f $script) -WorkingDirectory $projectRoot
$task = New-ScheduledTask -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description "Safely back up and retain SMAI data before a deferred scheduled Windows restart."
Register-ScheduledTask -TaskName $taskName -InputObject $task -Force | Out-Null
if ($ReplaceLegacyWeeklyRestart -and $null -ne $legacyTask) {
    Disable-ScheduledTask -TaskName "WeeklyRestart" -ErrorAction Stop | Out-Null
    Write-Host "[OK] Disabled legacy task: WeeklyRestart"
}
Write-Host "[OK] Registered: $taskName"
