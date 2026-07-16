[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateSet("once", "autofix-worker", "autofix-deploy-worker")]
    [string]$Mode,

    [Parameter(Mandatory)]
    [string]$PythonPath
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$script = Join-Path $projectRoot "incident_automation.py"

if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
    throw "Python executable was not found: $PythonPath"
}
if (-not (Test-Path -LiteralPath $script -PathType Leaf)) {
    throw "Incident Automation entry point was not found: $script"
}

Push-Location -LiteralPath $projectRoot
try {
    & $PythonPath $script $Mode
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
