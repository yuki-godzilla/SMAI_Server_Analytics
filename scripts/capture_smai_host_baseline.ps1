[CmdletBinding()]
param(
    [string]$RuntimeRoot = "C:\Users\user\workspace\SMAI_Projects\SMAI_Server_Runtime"
)

$ErrorActionPreference = "Stop"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$destination = Join-Path $RuntimeRoot "host_maintenance\baselines\$stamp"
New-Item -ItemType Directory -Path $destination -Force | Out-Null

function Get-AcPowerValue {
    param([string]$Subgroup, [string]$Setting)
    $line = (powercfg.exe /query SCHEME_CURRENT $Subgroup $Setting | Out-String).Split([Environment]::NewLine) |
        Where-Object { $_ -match "Current AC Power Setting Index|現在の AC 電源設定のインデックス" } |
        Select-Object -Last 1
    if ($line -match "0x([0-9a-fA-F]+)") {
        return [Convert]::ToInt32($Matches[1], 16)
    }
    return $null
}

$activeScheme = (powercfg.exe /getactivescheme | Out-String).Trim()
$schemeMatch = [regex]::Match($activeScheme, "[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}")
$hybridSleep = (powercfg.exe /query SCHEME_CURRENT SUB_SLEEP HYBRIDSLEEP | Out-String).Trim()
$sleepTimeout = (powercfg.exe /query SCHEME_CURRENT SUB_SLEEP STANDBYIDLE | Out-String).Trim()
$hibernateTimeout = (powercfg.exe /query SCHEME_CURRENT SUB_SLEEP HIBERNATEIDLE | Out-String).Trim()
$fastStartup = Get-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Power" -Name HiberbootEnabled -ErrorAction SilentlyContinue
$updateSettings = Get-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\WindowsUpdate\UX\Settings" -ErrorAction SilentlyContinue

[pscustomobject]@{
    captured_at = (Get-Date).ToString("o")
    active_power_scheme = $activeScheme
    active_power_scheme_guid = if ($schemeMatch.Success) { $schemeMatch.Value } else { $null }
    hybrid_sleep_ac = Get-AcPowerValue "SUB_SLEEP" "HYBRIDSLEEP"
    sleep_timeout_ac = Get-AcPowerValue "SUB_SLEEP" "STANDBYIDLE"
    hibernate_timeout_ac = Get-AcPowerValue "SUB_SLEEP" "HIBERNATEIDLE"
    hybrid_sleep = $hybridSleep
    sleep_timeout = $sleepTimeout
    hibernate_timeout = $hibernateTimeout
    fast_startup_enabled = $fastStartup.HiberbootEnabled
    active_hours_start = $updateSettings.ActiveHoursStart
    active_hours_end = $updateSettings.ActiveHoursEnd
} | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath (Join-Path $destination "power_and_update.json") -Encoding utf8

foreach ($taskName in "WeeklyRestart", "SMAI-Server-Analytics", "SmartMarketAI-Server-Autostart", "SmartMarketAI-Server-Watch") {
    $target = Join-Path $destination ("{0}.xml" -f $taskName)
    try {
        schtasks.exe /query /tn $taskName /xml | Set-Content -LiteralPath $target -Encoding unicode
    } catch {
        "Task query failed: $taskName" | Set-Content -LiteralPath (Join-Path $destination ("{0}.missing.txt" -f $taskName)) -Encoding utf8
    }
}

Write-Host "[SMAI] Host baseline captured: $destination"
