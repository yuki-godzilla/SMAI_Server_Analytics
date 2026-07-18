[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)]
    [string]$UserId,
    [string]$PythonPath = "",
    [switch]$DryRun
)

if ($PSVersionTable.PSEdition -ne "Desktop") {
    $windowsPowerShell = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
    if (-not (Test-Path -LiteralPath $windowsPowerShell)) {
        throw "Windows PowerShell 5.1 was not found: $windowsPowerShell"
    }

    $arguments = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", $PSCommandPath,
        "-UserId", $UserId
    )
    if ($PythonPath) {
        $arguments += @("-PythonPath", $PythonPath)
    }
    if ($DryRun) {
        $arguments += "-DryRun"
    }

    & $windowsPowerShell @arguments
    exit $LASTEXITCODE
}

$ErrorActionPreference = "Stop"
$taskName = "SMAI-Codex-Autofix-Worker"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = if ($PythonPath) { (Resolve-Path -LiteralPath $PythonPath).Path } else { (Get-Command python.exe -ErrorAction Stop).Source }
$runner = Join-Path $PSScriptRoot "run_incident_automation_task.ps1"
$hiddenRunner = Join-Path $PSScriptRoot "run_hidden_powershell.vbs"
$powershell = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$wscript = "$env:SystemRoot\System32\wscript.exe"
$config = Join-Path $projectRoot "config\codex_autofix.json"

if (-not (Test-Path -LiteralPath $runner -PathType Leaf)) {
    throw "Required hidden task runner was not found: $runner"
}
if (-not (Test-Path -LiteralPath $hiddenRunner -PathType Leaf)) {
    throw "Required non-console launcher was not found: $hiddenRunner"
}
if (-not (Test-Path -LiteralPath $config -PathType Leaf)) {
    throw "Required Autofix config was not found: $config"
}

$action = New-ScheduledTaskAction -Execute $wscript -Argument ('//B //Nologo "{0}" "{1}" -NoProfile -ExecutionPolicy Bypass -File "{2}" -Mode autofix-worker -PythonPath "{3}"' -f $hiddenRunner, $powershell, $runner, $python) -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger -Daily -At "00:00"
$repetition = New-CimInstance -ClassName MSFT_TaskRepetitionPattern `
    -Namespace Root\Microsoft\Windows\TaskScheduler `
    -ClientOnly `
    -Property @{ Interval = "PT5M"; Duration = "P1D"; StopAtDurationEnd = $false }
$trigger.Repetition = $repetition
$principal = New-ScheduledTaskPrincipal -UserId $UserId -LogonType Password -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 45) -StartWhenAvailable
$task = New-ScheduledTask -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description "Run one approval-gated Codex Autofix or merge lease in an isolated Analytics worktree."

if ($DryRun) {
    Write-Host "[DRY-RUN] Task: $taskName"
    Write-Host "[DRY-RUN] User: $UserId (must be a dedicated standard account)"
    Write-Host "[DRY-RUN] Action: hidden PowerShell -> $python incident_automation.py autofix-worker"
    Write-Host "[DRY-RUN] Config remains fail-closed unless enabled=true and mode=active."
    exit 0
}

if (-not $PSCmdlet.ShouldProcess($taskName, "Register dedicated Codex Autofix worker")) {
    exit 0
}

# Do not use Get-Credential here.  Its inbox module can fail to import on a
# host with duplicated TypeData registrations.  The host API is available
# without Microsoft.PowerShell.Security and keeps the password in the native
# Windows credential dialog rather than this script or its output.
$credential = $Host.UI.PromptForCredential(
    "SMAI Codex Autofix worker",
    "Enter the Windows password for the Autofix worker account.",
    $UserId,
    ""
)
if ($null -eq $credential) {
    throw "Autofix worker task registration was cancelled because no credential was provided."
}
Register-ScheduledTask -TaskName $taskName -InputObject $task -User $credential.UserName -Password $credential.GetNetworkCredential().Password -Force | Out-Null
Write-Host "[OK] Registered: $taskName"
Write-Host "[INFO] Autofix is still controlled by config/codex_autofix.json and per-Incident administrator leases."
