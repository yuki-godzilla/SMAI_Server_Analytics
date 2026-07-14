[CmdletBinding()]
param(
    [switch]$Replace
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = (Get-Command python.exe -ErrorAction Stop).Source
$script = Join-Path $projectRoot "incident_automation.py"

if (-not (Test-Path -LiteralPath $script -PathType Leaf)) {
    throw "Required script was not found: $script"
}

$arguments = @($script, "configure-gmail")
if ($Replace) {
    $arguments += "--replace"
}

Write-Host "[INFO] Gmail addresses are saved only under SMAI_Server_Runtime."
Write-Host "[INFO] The app password is prompted securely and stored only in Windows Credential Manager."
& $python @arguments
exit $LASTEXITCODE
