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
$startupLauncher = Join-Path $startupDirectory "SMAI Operations Workspace.cmd"
$powershell = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$launcherContents = @"
@echo off
start "" /b "$powershell" -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "$workspaceScript"
exit /b 0
"@
Set-Content -LiteralPath $startupLauncher -Value $launcherContents -Encoding ascii
if ($RunImmediately) {
    & $workspaceScript
    if (-not $?) { throw "Could not start the Operations Workspace." }
}
Write-Host "[OK] Registered user Startup launcher: $startupLauncher"
