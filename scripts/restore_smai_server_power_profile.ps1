[CmdletBinding()]
param(
    [string]$BaselinePath
)

$ErrorActionPreference = "Stop"
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Restoring server power settings requires an elevated PowerShell session. No setting was changed."
}
$runtimeRoot = "C:\Users\user\workspace\SMAI_Projects\SMAI_Server_Runtime"
if ([string]::IsNullOrWhiteSpace($BaselinePath)) {
    $BaselinePath = Get-ChildItem (Join-Path $runtimeRoot "host_maintenance\baselines") -Directory |
        Sort-Object Name -Descending |
        Select-Object -First 1 -ExpandProperty FullName
}
if ([string]::IsNullOrWhiteSpace($BaselinePath)) { throw "No host-maintenance baseline was found." }
$settingsPath = Join-Path $BaselinePath "power_and_update.json"
if (-not (Test-Path -LiteralPath $settingsPath)) { throw "Baseline settings were not found: $settingsPath" }
$settings = Get-Content -LiteralPath $settingsPath -Raw | ConvertFrom-Json
if (-not [string]::IsNullOrWhiteSpace([string]$settings.active_power_scheme_guid)) {
    powercfg.exe /setactive $settings.active_power_scheme_guid
}
foreach ($entry in @(
    @{ setting = "HYBRIDSLEEP"; value = $settings.hybrid_sleep_ac },
    @{ setting = "STANDBYIDLE"; value = $settings.sleep_timeout_ac },
    @{ setting = "HIBERNATEIDLE"; value = $settings.hibernate_timeout_ac }
)) {
    if ($null -ne $entry.value) {
        powercfg.exe /setacvalueindex SCHEME_CURRENT SUB_SLEEP $entry.setting ([int]$entry.value)
    }
}
powercfg.exe /setactive SCHEME_CURRENT
if ($null -ne $settings.fast_startup_enabled) {
    Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Power" -Name HiberbootEnabled -Type DWord -Value ([int]$settings.fast_startup_enabled)
}
if ($null -ne $settings.active_hours_start) {
    Set-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\WindowsUpdate\UX\Settings" -Name ActiveHoursStart -Type DWord -Value ([int]$settings.active_hours_start)
}
if ($null -ne $settings.active_hours_end) {
    Set-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\WindowsUpdate\UX\Settings" -Name ActiveHoursEnd -Type DWord -Value ([int]$settings.active_hours_end)
}
Write-Host "[OK] Restored power and update settings from: $BaselinePath"
