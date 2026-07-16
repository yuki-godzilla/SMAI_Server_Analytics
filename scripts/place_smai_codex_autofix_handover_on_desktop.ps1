[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$UserName = "SMAI-Codex-Autofix",
    [string]$RuntimeRoot = "C:\Users\user\workspace\SMAI_Projects\SMAI_Server_Runtime"
)

$ErrorActionPreference = "Stop"
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Place the handover document from an elevated Windows PowerShell session."
}

$source = Join-Path $RuntimeRoot "development_environment\handover\SMAI-Codex-Autofix_引継ぎ指示書.docx"
$desktop = Join-Path "C:\Users\$UserName" "Desktop"
$destination = Join-Path $desktop "SMAI-Codex-Autofix_引継ぎ指示書.docx"

if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
    throw "Handover document was not found: $source"
}
if (-not (Test-Path -LiteralPath "C:\Users\$UserName" -PathType Container)) {
    throw "Dedicated account profile was not found: C:\Users\$UserName"
}

if ($PSCmdlet.ShouldProcess($destination, "Copy the SMAI Codex Autofix handover document to the dedicated account desktop")) {
    New-Item -ItemType Directory -Path $desktop -Force | Out-Null
    Copy-Item -LiteralPath $source -Destination $destination -Force
    Write-Host "[OK] Placed on desktop: $destination"
}
