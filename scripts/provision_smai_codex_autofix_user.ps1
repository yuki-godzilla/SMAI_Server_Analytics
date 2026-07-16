[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$UserName = "SMAI-Codex-Autofix",
    [string]$RuntimeRoot = "C:\Users\user\workspace\SMAI_Projects\SMAI_Server_Runtime"
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)

if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Create this dedicated Autofix account from an elevated Windows PowerShell session."
}
if ($UserName -notmatch "^[A-Za-z0-9][A-Za-z0-9._-]{0,19}$") {
    throw "UserName must contain only letters, numbers, dots, underscores, and hyphens."
}
$existingAccount = Get-LocalUser -Name $UserName -ErrorAction SilentlyContinue
$password = $null
if (-not $existingAccount) {
    $password = Read-Host -Prompt "Set a strong password for $UserName" -AsSecureString
    if ($null -eq $password -or $password.Length -eq 0) {
        throw "A non-empty password is required."
    }
}

$incidentRoot = Join-Path $RuntimeRoot "incident_operations"
$targets = @($projectRoot, $incidentRoot)
$created = $false

try {
    if (-not $PSCmdlet.ShouldProcess($UserName, "Create dedicated limited Autofix account and grant scoped local access")) {
        exit 0
    }

    if (-not $existingAccount) {
        New-LocalUser -Name $UserName -Password $password -Description "SMAI Codex Autofix worker" -AccountNeverExpires | Out-Null
        $created = $true
    }
    $administrators = Get-LocalGroupMember -Group "Administrators" -ErrorAction SilentlyContinue
    if ($administrators | Where-Object { $_.Name -match "\\$([regex]::Escape($UserName))$" }) {
        throw "The dedicated Autofix account must not be a local Administrator: $UserName"
    }
    $users = Get-LocalGroupMember -Group "Users" -ErrorAction Stop
    if (-not ($users | Where-Object { $_.Name -match "\\$([regex]::Escape($UserName))$" })) {
        Add-LocalGroupMember -Group "Users" -Member $UserName -ErrorAction Stop
    }
    # The locally installed Codex CLI grants read/execute access through this
    # managed group. Its membership does not grant Administrator privileges.
    $codexSandboxUsers = Get-LocalGroup -Name "CodexSandboxUsers" -ErrorAction SilentlyContinue
    if ($null -ne $codexSandboxUsers) {
        $codexMembers = Get-LocalGroupMember -Group $codexSandboxUsers.Name -ErrorAction Stop
        if (-not ($codexMembers | Where-Object { $_.Name -match "\\$([regex]::Escape($UserName))$" })) {
            Add-LocalGroupMember -Group $codexSandboxUsers.Name -Member $UserName -ErrorAction Stop
        }
    }
    & net.exe user $UserName /passwordreq:yes | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Could not require a password for: $UserName"
    }
    New-Item -ItemType Directory -Path $incidentRoot -Force | Out-Null

    $grant = "{0}:(OI)(CI)M" -f "$env:COMPUTERNAME\$UserName"
    foreach ($target in $targets) {
        & icacls $target /grant $grant /T /C | Out-Null
        if ($LASTEXITCODE -gt 1) {
            throw "Could not grant scoped access to: $target"
        }
    }
}
catch {
    if ($created) {
        Remove-LocalUser -Name $UserName -ErrorAction SilentlyContinue
    }
    throw
}
finally {
    $password = $null
}

Write-Host "[OK] Dedicated standard account is ready: $UserName"
Write-Host "[NEXT] Sign in once as $UserName and complete the Codex login."
Write-Host "[NEXT] Keep config/codex_autofix.json disabled until the dedicated-account dry-run succeeds."
