[CmdletBinding()]
param(
    [switch]$Apply,
    [ValidateRange(0, 23)]
    [int]$ActiveHoursStart = 8,
    [ValidateRange(0, 23)]
    [int]$ActiveHoursEnd = 2
)

$ErrorActionPreference = "Stop"
if (-not $Apply) {
    Write-Host "[SMAI] Dry run only. Use -Apply to disable AC Hybrid Sleep and Fast Startup, and set Windows active hours."
    exit 0
}
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Applying the server power profile requires an elevated PowerShell session. No setting was changed."
}
powercfg.exe /setactive SCHEME_BALANCED
powercfg.exe /setacvalueindex SCHEME_CURRENT SUB_SLEEP HYBRIDSLEEP 0
powercfg.exe /setacvalueindex SCHEME_CURRENT SUB_SLEEP STANDBYIDLE 0
powercfg.exe /setacvalueindex SCHEME_CURRENT SUB_SLEEP HIBERNATEIDLE 0
powercfg.exe /setactive SCHEME_CURRENT
Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Power" -Name HiberbootEnabled -Type DWord -Value 0
New-Item -Path "HKLM:\SOFTWARE\Microsoft\WindowsUpdate\UX\Settings" -Force | Out-Null
Set-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\WindowsUpdate\UX\Settings" -Name ActiveHoursStart -Type DWord -Value $ActiveHoursStart
Set-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\WindowsUpdate\UX\Settings" -Name ActiveHoursEnd -Type DWord -Value $ActiveHoursEnd
Write-Host "[OK] Applied balanced always-on profile: Hybrid Sleep off, Fast Startup off, Active Hours $ActiveHoursStart`:00-$ActiveHoursEnd`:00."
