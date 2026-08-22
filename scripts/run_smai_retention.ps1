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
$retentionScript = Join-Path $projectRoot "retention.py"

if (-not (Test-Path -LiteralPath $retentionScript -PathType Leaf)) {
    throw "Retention entry point was not found: $retentionScript"
}

& $python $retentionScript
exit $LASTEXITCODE
