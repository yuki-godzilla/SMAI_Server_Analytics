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

$source = Join-Path $RuntimeRoot "development_environment\handover\SMAI-Codex-Autofix-Handover.docx"
$desktop = Join-Path "C:\Users\$UserName" "Desktop"
$destination = Join-Path $desktop "SMAI-Codex-Autofix-Handover.docx"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$workspaceLauncher = Join-Path $PSScriptRoot "launch_smai_codex_autofix_workspace.ps1"
$code = "C:\Users\user\AppData\Local\Programs\Microsoft VS Code\Code.exe"
$codex = "C:\Users\user\AppData\Local\Programs\OpenAI\Codex\bin\codex.exe"
$windowsPowerShell = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"

if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
    throw "Handover document was not found: $source"
}
if (-not (Test-Path -LiteralPath "C:\Users\$UserName" -PathType Container)) {
    throw "Dedicated account profile was not found: C:\Users\$UserName"
}
foreach ($path in @($workspaceLauncher, $code, $codex, $windowsPowerShell)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Required desktop tool was not found: $path"
    }
}

if ($PSCmdlet.ShouldProcess($destination, "Copy the SMAI Codex Autofix handover document to the dedicated account desktop")) {
    New-Item -ItemType Directory -Path $desktop -Force | Out-Null
    Copy-Item -LiteralPath $source -Destination $destination -Force
    $shell = New-Object -ComObject WScript.Shell
    $shortcuts = @(
        @("SMAI-Shared-Developer-Workspace.lnk", $windowsPowerShell, "-NoProfile -ExecutionPolicy Bypass -File `"$workspaceLauncher`"", $projectRoot, "Open the SMAI Server Analytics shared VS Code workspace."),
        @("SMAI-Codex-CLI.lnk", $windowsPowerShell, "-NoExit -NoProfile -Command `"Set-Location -LiteralPath '$projectRoot'; & '$codex'`"", $projectRoot, "Open the dedicated-account Codex CLI."),
        @("SMAI-Codex-Autofix-Handover.lnk", $destination, "", "", "Open the dedicated-account handover guide.")
    )
    foreach ($shortcut in $shortcuts) {
        $link = $shell.CreateShortcut((Join-Path $desktop $shortcut[0]))
        $link.TargetPath = $shortcut[1]
        $link.Arguments = $shortcut[2]
        $link.WorkingDirectory = $shortcut[3]
        $link.Description = $shortcut[4]
        $link.Save()
    }
    @("[InternetShortcut]", "URL=https://chatgpt.com") | Set-Content -LiteralPath (Join-Path $desktop "ChatGPT-Web.url") -Encoding ascii
    Write-Host "[OK] Placed on desktop: $destination"
    Write-Host "[OK] Added desktop launchers: shared workspace, Codex CLI, ChatGPT Web, and handover guide."
}
