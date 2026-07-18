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
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($startupLauncher)
$shortcut.TargetPath = $powershell
$shortcut.Arguments = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$startScript`" -StartupDelaySeconds 45"
$shortcut.WorkingDirectory = $projectRoot
$shortcut.WindowStyle = 7
$shortcut.Save()
if (Test-Path -LiteralPath $legacyLauncher -PathType Leaf) {
    Remove-Item -LiteralPath $legacyLauncher -Force
    Write-Host "[SMAI] Replaced CMD Startup launcher with PowerShell shortcut."
}

$legacyTaskName = "SMAI-Server-Analytics"
$legacyTask = Get-ScheduledTask -TaskName $legacyTaskName -ErrorAction SilentlyContinue
if ($null -ne $legacyTask) {
    $legacyActions = ($legacyTask.Actions | ForEach-Object { "$($_.Execute) $($_.Arguments)" }) -join " "
    if ($legacyActions -match "(?i)run_analytics_web\.bat") {
        Disable-ScheduledTask -TaskName $legacyTaskName | Out-Null
        Write-Host "[SMAI] Disabled legacy CMD task: $legacyTaskName"
    }
}
if ($RunImmediately) {
    & $startScript -StartupDelaySeconds 0
    if (-not $?) { throw "Could not start the Analytics launcher." }
}
Write-Host "[OK] Registered user Startup launcher: $startupLauncher"
