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
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($startupLauncher)
$shortcut.TargetPath = $powershell
$shortcut.Arguments = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$workspaceScript`""
$shortcut.WorkingDirectory = $projectRoot
$shortcut.WindowStyle = 7
$shortcut.Save()
if (Test-Path -LiteralPath $legacyLauncher -PathType Leaf) {
    Remove-Item -LiteralPath $legacyLauncher -Force
    Write-Host "[SMAI] Replaced CMD Startup launcher with PowerShell shortcut."
}
if ($RunImmediately) {
    & $workspaceScript
    if (-not $?) { throw "Could not start the Operations Workspace." }
}
Write-Host "[OK] Registered user Startup launcher: $startupLauncher"
