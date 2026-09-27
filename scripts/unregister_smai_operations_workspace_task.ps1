[CmdletBinding()]
param()

$startupDirectory = [Environment]::GetFolderPath([Environment+SpecialFolder]::Startup)
$taskName = "SMAI-Operations-Workspace"
$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($null -ne $task) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host "[OK] Removed logon task: $taskName"
} else {
    Write-Host "[SMAI] Logon task is not registered: $taskName"
}

foreach ($launcherName in @("SMAI Operations Workspace.lnk", "SMAI Operations Workspace.cmd")) {
    $startupLauncher = Join-Path $startupDirectory $launcherName
    if (Test-Path -LiteralPath $startupLauncher -PathType Leaf) {
        Remove-Item -LiteralPath $startupLauncher -Force
        Write-Host "[OK] Removed user Startup launcher: $startupLauncher"
    } else {
        Write-Host "[SMAI] User Startup launcher is not registered: $startupLauncher"
    }
}
