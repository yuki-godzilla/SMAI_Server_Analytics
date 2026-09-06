[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$startupDirectory = [Environment]::GetFolderPath([Environment+SpecialFolder]::Startup)
$taskName = "SMAI-Server-Analytics"
$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($null -ne $task) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host "[OK] Removed Analytics logon task: $taskName"
} else {
    Write-Host "[SMAI] Analytics logon task is not registered: $taskName"
}

foreach ($launcherName in @("SMAI Analytics Autostart.lnk", "SMAI Analytics Autostart.cmd")) {
    $launcher = Join-Path $startupDirectory $launcherName
    if (Test-Path -LiteralPath $launcher -PathType Leaf) {
        Remove-Item -LiteralPath $launcher -Force
        Write-Host "[OK] Removed superseded Startup launcher: $launcher"
    }
}
