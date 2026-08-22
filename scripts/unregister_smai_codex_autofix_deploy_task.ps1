[CmdletBinding(SupportsShouldProcess)]
param()

$ErrorActionPreference = "Stop"
$taskName = "SMAI-Codex-Autofix-Deploy"

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    if ($PSCmdlet.ShouldProcess($taskName, "Unregister approval-gated Analytics deployment executor")) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "[OK] Unregistered: $taskName"
    }
} else {
    Write-Host "[INFO] Task is not registered: $taskName"
}
