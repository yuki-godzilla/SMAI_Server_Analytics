[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$analyticsPython = Join-Path $projectRoot "venv_SMAI_Analytics\Scripts\python.exe"
$compatibilityPython = "C:\Users\user\workspace\SMAI_Projects\Smart_Market_AI\venv_SMAI\Scripts\python.exe"
$python = if (Test-Path -LiteralPath $analyticsPython -PathType Leaf) {
    $analyticsPython
} elseif (Test-Path -LiteralPath $compatibilityPython -PathType Leaf) {
    $compatibilityPython
} else {
    throw "Analytics Python was not found."
}
$healthScript = Join-Path $projectRoot "health.py"
$taskObserver = Join-Path $projectRoot "observe_tasks.py"

if (-not (Test-Path -LiteralPath $healthScript -PathType Leaf)) {
    throw "Analytics health entry point was not found: $healthScript"
}
if (-not (Test-Path -LiteralPath $taskObserver -PathType Leaf)) {
    throw "Scheduled-task observer was not found: $taskObserver"
}

& $python $healthScript
$healthExit = $LASTEXITCODE
& $python $taskObserver | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Warning "[SMAI] Scheduled-task observation could not be recorded."
}
exit $healthExit
