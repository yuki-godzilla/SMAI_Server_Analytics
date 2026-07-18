[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = (Get-Command python.exe -ErrorAction Stop).Source
$script = Join-Path $projectRoot "incident_automation.py"

if (-not (Test-Path -LiteralPath $script -PathType Leaf)) {
    throw "Required script was not found: $script"
}

Write-Host "[WARN] This sends one external Gmail test message to the fixed local recipient."
& $python $script test-gmail --confirm
exit $LASTEXITCODE
