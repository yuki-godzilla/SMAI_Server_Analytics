[CmdletBinding()]
param(
    [ValidateRange(1, 28)]
    [int]$DayOfMonth = 1,

    [ValidatePattern('^(?:[01]\\d|2[0-3]):[0-5]\\d$')]
    [string]$At = "02:00",

    [string]$PythonPath
)

$ErrorActionPreference = "Stop"
$taskName = "SMAI-Backup-Restore-Smoke"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$runner = Join-Path $projectRoot "scripts\run_backup_restore_smoke.ps1"
$powershell = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$analyticsPython = Join-Path $projectRoot "venv_SMAI_Analytics\Scripts\python.exe"
$compatibilityPython = "C:\Users\user\workspace\SMAI_Projects\Smart_Market_AI\venv_SMAI\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $runner -PathType Leaf)) {
    throw "Required smoke runner was not found: $runner"
}
if (-not [string]::IsNullOrWhiteSpace($PythonPath)) {
    $python = (Resolve-Path -LiteralPath $PythonPath -ErrorAction Stop).Path
} elseif (Test-Path -LiteralPath $analyticsPython -PathType Leaf) {
    $python = $analyticsPython
} elseif (Test-Path -LiteralPath $compatibilityPython -PathType Leaf) {
    $python = $compatibilityPython
} else {
    throw "Streamlit-enabled Python was not found. Run setup\\setup.bat before registering Backup Restore Smoke."
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$taskCommand = ('"{0}" -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "{1}"' -f $powershell, $runner)
$arguments = @(
    "/Create", "/TN", $taskName, "/TR", $taskCommand,
    "/SC", "MONTHLY", "/D", $DayOfMonth, "/ST", $At,
    "/RU", $identity.Name, "/IT", "/RL", "LIMITED", "/F"
)

& schtasks.exe @arguments
if ($LASTEXITCODE -ne 0) {
    throw "Could not register $taskName."
}
Write-Host "[OK] Registered: $taskName (day $DayOfMonth at $At while $($identity.Name) is logged on)"
Write-Host "[INFO] Python resolution: $python"
Write-Host "[INFO] The smoke check creates a backup and verifies an isolated restore; it never restores over SMAI data."
