[CmdletBinding()]
param(
    [switch]$DryRun,
    [switch]$NoRestart,
    [ValidateRange(30, 900)]
    [int]$RestartDelaySeconds = 120
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$analyticsPython = Join-Path $projectRoot "venv_SMAI_Analytics\Scripts\python.exe"
$compatibilityPython = "C:\Users\user\workspace\SMAI_Projects\Smart_Market_AI\venv_SMAI\Scripts\python.exe"
$python = if (Test-Path -LiteralPath $analyticsPython) { $analyticsPython } elseif (Test-Path -LiteralPath $compatibilityPython) { $compatibilityPython } else { throw "Analytics Python was not found." }

& $python (Join-Path $projectRoot "host_maintenance.py") preflight
$preflightExit = $LASTEXITCODE
if ($preflightExit -eq 20) {
    Write-Host "[SMAI] Host maintenance deferred by the fail-closed preflight."
    exit 0
}
if ($preflightExit -ne 0) {
    throw "Host-maintenance preflight failed (exit=$preflightExit)."
}
if ($DryRun) {
    Write-Host "[SMAI] Host-maintenance dry run completed; no backup, retention, or restart was requested."
    exit 0
}

& $python (Join-Path $projectRoot "backup.py") create
if ($LASTEXITCODE -ne 0) { throw "Pre-restart backup failed." }
& $python (Join-Path $projectRoot "retention.py")
if ($LASTEXITCODE -ne 0) { throw "Retention failed." }
if ($NoRestart) {
    Write-Host "[SMAI] Backup and retention completed; restart was suppressed."
    exit 0
}

$comment = "SMAI scheduled maintenance restart; cancel with shutdown /a if required."
& shutdown.exe /r /t $RestartDelaySeconds /d p:4:1 /c $comment
if ($LASTEXITCODE -ne 0) { throw "Windows restart request failed." }
Write-Host "[SMAI] Windows restart was requested with a $RestartDelaySeconds second grace period."
