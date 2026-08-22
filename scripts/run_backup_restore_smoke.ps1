[CmdletBinding()]
param(
    [string]$PythonPath
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$analyticsPython = Join-Path $projectRoot "venv_SMAI_Analytics\Scripts\python.exe"
$compatibilityPython = "C:\Users\user\workspace\SMAI_Projects\Smart_Market_AI\venv_SMAI\Scripts\python.exe"
$backupScript = Join-Path $projectRoot "backup.py"

if (-not (Test-Path -LiteralPath $backupScript -PathType Leaf)) {
    throw "Required backup entry point was not found: $backupScript"
}

if (-not [string]::IsNullOrWhiteSpace($PythonPath)) {
    $python = (Resolve-Path -LiteralPath $PythonPath -ErrorAction Stop).Path
} elseif (Test-Path -LiteralPath $analyticsPython -PathType Leaf) {
    $python = $analyticsPython
} elseif (Test-Path -LiteralPath $compatibilityPython -PathType Leaf) {
    $python = $compatibilityPython
} else {
    throw "Streamlit-enabled Python was not found. Run setup\\setup.bat before running the restore smoke check."
}

Push-Location -LiteralPath $projectRoot
try {
    & $python $backupScript smoke
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
