[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$PythonPath = "",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$taskName = "SMAI-Codex-Autofix-Deploy"
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

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-ScheduledTaskPrincipal -UserId $identity.Name -LogonType Interactive -RunLevel Limited
$action = New-ScheduledTaskAction -Execute $python -Argument ('"{0}" autofix-deploy-worker' -f $script) -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger -Daily -At "00:00"
$repetition = New-CimInstance -ClassName MSFT_TaskRepetitionPattern `
    -Namespace Root\Microsoft\Windows\TaskScheduler `
    -ClientOnly `
    -Property @{ Interval = "PT1M"; Duration = "P1D"; StopAtDurationEnd = $false }
$trigger.Repetition = $repetition
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 15) -StartWhenAvailable
$task = New-ScheduledTask -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description "Apply one separately approved Analytics Autofix deployment, verify health, and revert on failure."

if ($DryRun) {
    Write-Host "[DRY-RUN] Task: $taskName"
    Write-Host "[DRY-RUN] User: current interactive Analytics owner (limited token)"
    Write-Host "[DRY-RUN] Action: $python $script autofix-deploy-worker"
    Write-Host "[DRY-RUN] Deployment remains disabled unless enabled=true, mode=active, and deployment_enabled=true."
    exit 0
}

if (-not $PSCmdlet.ShouldProcess($taskName, "Register approval-gated Analytics deployment executor")) {
    exit 0
}

Register-ScheduledTask -TaskName $taskName -InputObject $task -Force | Out-Null
Write-Host "[OK] Registered: $taskName"
Write-Host "[INFO] This task can restart only Analytics; visual review and Git push remain manual."
