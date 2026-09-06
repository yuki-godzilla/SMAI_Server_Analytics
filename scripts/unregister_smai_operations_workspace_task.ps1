[CmdletBinding()]
param()

$startupDirectory = [Environment]::GetFolderPath([Environment+SpecialFolder]::Startup)
foreach ($launcherName in @("SMAI Operations Workspace.lnk", "SMAI Operations Workspace.cmd")) {
    $startupLauncher = Join-Path $startupDirectory $launcherName
    if (Test-Path -LiteralPath $startupLauncher -PathType Leaf) {
        Remove-Item -LiteralPath $startupLauncher -Force
        Write-Host "[OK] Removed user Startup launcher: $startupLauncher"
    } else {
        Write-Host "[SMAI] User Startup launcher is not registered: $startupLauncher"
    }
}
