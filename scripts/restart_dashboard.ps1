[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$dashboardPath = Join-Path $projectRoot "dashboard.py"
$startScript = Join-Path $projectRoot "run_dashboard.bat"
$windowTitle = "SMAI Analytics  |  Operations Console"

if (-not (Test-Path -LiteralPath $dashboardPath -PathType Leaf)) {
    throw "Dashboard entry point was not found: $dashboardPath"
}
if (-not (Test-Path -LiteralPath $startScript -PathType Leaf)) {
    throw "Dashboard launcher was not found: $startScript"
}

$escapedDashboardPath = [regex]::Escape($dashboardPath)
$windowProcesses = Get-Process -ErrorAction SilentlyContinue |
    Where-Object { $_.ProcessName -like "python*" -and $_.MainWindowTitle -eq $windowTitle }
$commandProcesses = Get-CimInstance Win32_Process -ErrorAction Stop |
    Where-Object {
        $_.Name -like "python*.exe" -and
        $_.CommandLine -match $escapedDashboardPath
    }
$processes = @($windowProcesses) + @($commandProcesses | ForEach-Object {
    Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue
}) | Where-Object { $null -ne $_ } | Sort-Object Id -Unique

foreach ($process in $processes) {
    Stop-Process -Id $process.Id -Force -ErrorAction Stop
    Write-Host "[SMAI] Stopped dashboard process: $($process.Id)"
}

Start-Process -FilePath $env:ComSpec -ArgumentList @("/d", "/c", "`"$startScript`"") -WorkingDirectory $projectRoot
Write-Host "[SMAI] Dashboard restart requested."
