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

if (-not (Test-Path -LiteralPath $healthScript -PathType Leaf)) {
    throw "Analytics health entry point was not found: $healthScript"
}

& $python $healthScript
exit $LASTEXITCODE
