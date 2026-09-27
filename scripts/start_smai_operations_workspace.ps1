[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$browserScript = Join-Path $PSScriptRoot "open_smai_service_pages.ps1"
$layoutScript = Join-Path $PSScriptRoot "arrange_smai_operations_workspace.ps1"
foreach ($path in @($browserScript, $layoutScript)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Required workspace script was not found: $path"
    }
}

# At logon, open only the two browser-based operations surfaces.  Service
# processes remain hidden and their health is checked by the browser launcher.
& $browserScript -StartupDelaySeconds 10 -WaitSeconds 180
try {
    & $layoutScript
} catch {
    # The web pages remain usable when a monitor is disconnected or Windows
    # temporarily rejects a layout request at logon.
    Write-Warning "SMAI workspace layout was not applied: $($_.Exception.Message)"
}
