[CmdletBinding()]
param(
    [switch]$RunImmediately
)

$ErrorActionPreference = "Stop"
$taskName = "SMAI-Host-Monitor"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$script = Join-Path $PSScriptRoot "run_smai_host_monitor.ps1"
$powershell = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"

if (-not (Test-Path -LiteralPath $script -PathType Leaf)) {
    throw "Host monitor launcher was not found: $script"
}

$taskCommand = ('"{0}" -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "{1}"' -f $powershell, $script)
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
