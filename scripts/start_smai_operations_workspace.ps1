[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$logDir = Join-Path $projectRoot "logs"
$logFile = Join-Path $logDir "workspace.log"
$browserScript = Join-Path $PSScriptRoot "open_smai_service_pages.ps1"
$layoutScript = Join-Path $PSScriptRoot "arrange_smai_operations_workspace.ps1"

New-Item -ItemType Directory -Force -Path $logDir | Out-Null

function Write-WorkspaceLog {
    param([string]$Message)
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -LiteralPath $logFile -Value "$stamp $Message" -Encoding UTF8
}

foreach ($path in @($browserScript, $layoutScript)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        Write-WorkspaceLog "ERROR Required workspace script was not found: $path"
        throw "Required workspace script was not found: $path"
    }
}

try {
    Write-WorkspaceLog "START SMAI Workspace launcher invoked."
    & $browserScript -StartupDelaySeconds 5 -WaitSeconds 180
    & $layoutScript -MaxWaitSeconds 90 -PollSeconds 2
    Write-WorkspaceLog "OK SMAI Workspace ready."
} catch {
    Write-WorkspaceLog "ERROR $($_.Exception.Message)"
    throw
}
