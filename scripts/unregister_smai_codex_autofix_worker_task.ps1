[CmdletBinding(SupportsShouldProcess)]
param()

$ErrorActionPreference = "Stop"
$taskName = "SMAI-Codex-Autofix-Worker"

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    if ($PSCmdlet.ShouldProcess($taskName, "Unregister Codex Autofix worker")) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "[OK] Unregistered: $taskName"
    }
} else {
    Write-Host "[INFO] Task is not registered: $taskName"
}
