[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$taskName = "SMAI-Incident-Automation"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = (Get-Command python.exe -ErrorAction Stop).Source
$script = Join-Path $projectRoot "incident_automation.py"

if (-not (Test-Path -LiteralPath $script -PathType Leaf)) {
    throw "Required script was not found: $script"
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-ScheduledTaskPrincipal -UserId $identity.Name -LogonType Interactive -RunLevel Limited
$trigger = New-ScheduledTaskTrigger -Daily -At "00:00"
$repetition = New-CimInstance -ClassName MSFT_TaskRepetitionPattern `
    -Namespace Root\Microsoft\Windows\TaskScheduler `
    -ClientOnly `
    -Property @{ Interval = "PT5M"; Duration = "P1D"; StopAtDurationEnd = $false }
$trigger.Repetition = $repetition
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 4) -StartWhenAvailable
$action = New-ScheduledTaskAction -Execute $python -Argument ('"{0}" once' -f $script) -WorkingDirectory $projectRoot
$task = New-ScheduledTask -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description "Detect SMAI critical health alerts, create approval-gated local Codex drafts, and deliver configured Gmail notifications."

Register-ScheduledTask -TaskName $taskName -InputObject $task -Force | Out-Null
Write-Host "[OK] Registered: $taskName (every 5 minutes while logged on)"
Write-Host "[INFO] This task never edits SMAI. Gmail delivery remains disabled until the local Credential Manager setup succeeds."
