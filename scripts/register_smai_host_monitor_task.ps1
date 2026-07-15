[CmdletBinding()]
param(
    [switch]$RunImmediately
)

$ErrorActionPreference = "Stop"
$taskName = "SMAI-Host-Monitor"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$analyticsPython = Join-Path $projectRoot "venv_SMAI_Analytics\Scripts\python.exe"
$compatibilityPython = "C:\Users\user\workspace\SMAI_Projects\Smart_Market_AI\venv_SMAI\Scripts\python.exe"
$python = if (Test-Path -LiteralPath $analyticsPython) { $analyticsPython } elseif (Test-Path -LiteralPath $compatibilityPython) { $compatibilityPython } else { throw "Analytics Python was not found." }
$script = Join-Path $projectRoot "health.py"

$taskCommand = ('"{0}" "{1}"' -f $python, $script)
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if ($principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    & schtasks.exe /create /tn $taskName /sc minute /mo 5 /tr $taskCommand /ru SYSTEM /rl HIGHEST /f
    $runContext = "SYSTEM"
} else {
    & schtasks.exe /create /tn $taskName /sc minute /mo 5 /tr $taskCommand /ru $identity.Name /it /rl LIMITED /f
    $runContext = "interactive user"
}
if ($LASTEXITCODE -ne 0) { throw "Could not register $taskName." }
if ($RunImmediately) {
    & schtasks.exe /run /tn $taskName
    if ($LASTEXITCODE -ne 0) { throw "Could not start $taskName." }
}
Write-Host "[OK] Registered: $taskName ($runContext, every 5 minutes)"
