[CmdletBinding()]
param(
    [switch]$RunImmediately
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$workspaceScript = Join-Path $projectRoot "scripts\start_smai_operations_workspace.ps1"
if (-not (Test-Path -LiteralPath $workspaceScript -PathType Leaf)) {
    throw "Workspace launcher was not found: $workspaceScript"
}

$startupDirectory = [Environment]::GetFolderPath([Environment+SpecialFolder]::Startup)
$startupLauncher = Join-Path $startupDirectory "SMAI Operations Workspace.lnk"
$legacyLauncher = Join-Path $startupDirectory "SMAI Operations Workspace.cmd"
$powershell = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$taskName = "SMAI-Operations-Workspace"

# A single scheduled task avoids duplicate browser launches caused by legacy
# Startup-folder entries.
foreach ($launcher in @($startupLauncher, $legacyLauncher)) {
    if (Test-Path -LiteralPath $launcher -PathType Leaf) {
        Remove-Item -LiteralPath $launcher -Force
        Write-Host "[SMAI] Removed superseded Startup launcher: $launcher"
    }
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$action = New-ScheduledTaskAction `
    -Execute $powershell `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$workspaceScript`"" `
    -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $identity.Name
$trigger.Delay = "PT1M"
$principal = New-ScheduledTaskPrincipal `
    -UserId $identity.Name `
    -LogonType Interactive `
    -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
    -StartWhenAvailable
$task = New-ScheduledTask `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description "Open and arrange the SMAI Main and Analytics web applications after user logon."
Register-ScheduledTask -TaskName $taskName -InputObject $task -Force -ErrorAction Stop | Out-Null

if ($RunImmediately) {
    & $workspaceScript
    if (-not $?) { throw "Could not start the Operations Workspace." }
}
Write-Host "[OK] Registered logon task: $taskName"
