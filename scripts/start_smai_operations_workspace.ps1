[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$promptScript = Join-Path $PSScriptRoot "show_smai_service_prompt.ps1"
$browserScript = Join-Path $PSScriptRoot "open_smai_service_pages.ps1"
$layoutScript = Join-Path $PSScriptRoot "arrange_smai_operations_workspace.ps1"
foreach ($path in @($promptScript, $browserScript, $layoutScript)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Required workspace script was not found: $path"
    }
}

$powershell = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
# Server processes stay hidden.  The two visible, color-coded PowerShell
# prompts provide one status surface each for Main and Analytics.
foreach ($service in @("Main", "Analytics")) {
    $arguments = @(
        "-NoExit", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$promptScript`"",
        "-Service", $service, "-Watch"
    )
    Start-Process -FilePath $powershell -ArgumentList $arguments
}

& $browserScript -StartupDelaySeconds 10 -WaitSeconds 180
try {
    & $layoutScript
} catch {
    # The service prompts and web pages remain usable when a monitor is
    # disconnected or Windows temporarily rejects a layout request at logon.
    Write-Warning "SMAI workspace layout was not applied: $($_.Exception.Message)"
}
