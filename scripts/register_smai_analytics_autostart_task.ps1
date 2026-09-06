[CmdletBinding()]
param(
    [switch]$RunImmediately
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$startScript = Join-Path $projectRoot "scripts\start_smai_analytics_service.ps1"

if (-not (Test-Path -LiteralPath $startScript -PathType Leaf)) {
    throw "Required script was not found: $startScript"
}

$startupDirectory = [Environment]::GetFolderPath([Environment+SpecialFolder]::Startup)
$startupLauncher = Join-Path $startupDirectory "SMAI Analytics Autostart.lnk"
$legacyLauncher = Join-Path $startupDirectory "SMAI Analytics Autostart.cmd"
$powershell = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$taskName = "SMAI-Server-Analytics"

# Startup-folder shortcuts and the old CMD task both race to bind TCP 8502 at
# logon.  Keep one user-owned, health-aware scheduled task as the sole path.
foreach ($launcher in @($startupLauncher, $legacyLauncher)) {
    if (Test-Path -LiteralPath $launcher -PathType Leaf) {
        Remove-Item -LiteralPath $launcher -Force
        Write-Host "[SMAI] Removed superseded Startup launcher: $launcher"
    }
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$userId = $identity.Name
$action = New-ScheduledTaskAction `
    -Execute $powershell `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$startScript`"" `
    -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $userId
$trigger.Delay = "PT1M"
$principal = New-ScheduledTaskPrincipal `
    -UserId $userId `
    -LogonType Interactive `
    -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -RestartCount 1 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
    -StartWhenAvailable
$task = New-ScheduledTask `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description "Start the SMAI Analytics Web Operations Console after user logon."
Register-ScheduledTask -TaskName $taskName -InputObject $task -Force -ErrorAction Stop | Out-Null

if ($RunImmediately) {
    & $startScript -StartupDelaySeconds 0
    if (-not $?) { throw "Could not start the Analytics launcher." }
}
Write-Host "[OK] Registered health-aware logon task: $taskName"
