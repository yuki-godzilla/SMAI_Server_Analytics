[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$taskName = "SMAI-Runtime-Retention"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$script = Join-Path $PSScriptRoot "run_smai_retention.ps1"
$hiddenRunner = Join-Path $PSScriptRoot "run_hidden_powershell.vbs"
$powershell = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$wscript = "$env:SystemRoot\System32\wscript.exe"

foreach ($path in @($script, $hiddenRunner)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Required retention task file was not found: $path"
    }
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-ScheduledTaskPrincipal -UserId $identity.Name -LogonType Interactive -RunLevel Limited
$trigger = New-ScheduledTaskTrigger -Daily -At "03:45"
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 10) -StartWhenAvailable
$arguments = ('//B //Nologo "{0}" "{1}" -NoProfile -ExecutionPolicy Bypass -File "{2}"' -f $hiddenRunner, $powershell, $script)
$action = New-ScheduledTaskAction -Execute $wscript -Argument $arguments -WorkingDirectory $projectRoot
$task = New-ScheduledTask -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description "Apply the existing local-only SMAI Runtime retention policy once per day."

Register-ScheduledTask -TaskName $taskName -InputObject $task -Force | Out-Null
Write-Host "[OK] Registered: $taskName (daily at 03:45 while logged on)"
