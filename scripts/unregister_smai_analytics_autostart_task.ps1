[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$startupDirectory = [Environment]::GetFolderPath([Environment+SpecialFolder]::Startup)
$startupLauncher = Join-Path $startupDirectory "SMAI Analytics Autostart.cmd"
if (Test-Path -LiteralPath $startupLauncher) {
    Remove-Item -LiteralPath $startupLauncher -Force
    Write-Host "[OK] Removed user Startup launcher: $startupLauncher"
} else {
    Write-Host "[SMAI] User Startup launcher is not registered: $startupLauncher"
}
