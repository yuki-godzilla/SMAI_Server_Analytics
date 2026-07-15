[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)]
    [string]$UserId,
    [string]$PythonPath = "",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$taskName = "SMAI-Codex-Autofix-Worker"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = if ($PythonPath) { (Resolve-Path -LiteralPath $PythonPath).Path } else { (Get-Command python.exe -ErrorAction Stop).Source }
$script = Join-Path $projectRoot "incident_automation.py"
$config = Join-Path $projectRoot "config\codex_autofix.json"

if (-not (Test-Path -LiteralPath $script -PathType Leaf)) {
    throw "Required script was not found: $script"
}
if (-not (Test-Path -LiteralPath $config -PathType Leaf)) {
    throw "Required Autofix config was not found: $config"
}

$action = New-ScheduledTaskAction -Execute $python -Argument ('"{0}" autofix-worker' -f $script) -WorkingDirectory $projectRoot
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
    Write-Host "[DRY-RUN] Action: $python $script autofix-worker"
    Write-Host "[DRY-RUN] Config remains fail-closed unless enabled=true and mode=active."
    exit 0
}

if (-not $PSCmdlet.ShouldProcess($taskName, "Register dedicated Codex Autofix worker")) {
    exit 0
}

$credential = Get-Credential -UserName $UserId -Message "Enter the dedicated standard-account credential for the Autofix task."
Register-ScheduledTask -TaskName $taskName -InputObject $task -User $credential.UserName -Password $credential.GetNetworkCredential().Password -Force | Out-Null
Write-Host "[OK] Registered: $taskName"
Write-Host "[INFO] Autofix is still controlled by config/codex_autofix.json and per-Incident administrator leases."
