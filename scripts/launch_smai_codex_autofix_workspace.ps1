[CmdletBinding()]
param(
    [switch]$InstallRecommendedExtensions,
    [switch]$NoLaunch
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$runtimeRoot = "C:\Users\user\workspace\SMAI_Projects\SMAI_Server_Runtime\development_environment"
$codeExecutable = "C:\Users\user\AppData\Local\Programs\Microsoft VS Code\Code.exe"
$codeCli = "C:\Users\user\AppData\Local\Programs\Microsoft VS Code\bin\code.cmd"
$python = "C:\Users\user\AppData\Local\Programs\Python\Python312\python.exe"
$git = "C:\Program Files\Git\cmd\git.exe"
$codex = "C:\Users\user\AppData\Local\Programs\OpenAI\Codex\bin\codex.exe"

foreach ($tool in @($codeExecutable, $codeCli, $python, $git, $codex)) {
    if (-not (Test-Path -LiteralPath $tool)) {
        throw "Required development tool was not found: $tool"
    }
}

$userDataDirectory = Join-Path $env:LOCALAPPDATA "SMAI-Shared-VSCode"
$extensionsDirectory = Join-Path $runtimeRoot "vscode-extensions"
$sharedSettingsPath = Join-Path $runtimeRoot "vscode-shared-settings.json"
New-Item -ItemType Directory -Path $userDataDirectory, $extensionsDirectory -Force | Out-Null

$settings = @{
    "python.defaultInterpreterPath" = $python
    "python.terminal.activateEnvironment" = $false
    "terminal.integrated.defaultProfile.windows" = "PowerShell"
    "terminal.integrated.enablePersistentSessions" = $true
    "terminal.integrated.persistentSessionReviveProcess" = "onExitAndWindowClose"
    "terminal.integrated.hideOnStartup" = "never"
    "workbench.colorTheme" = "Dark Modern"
    "workbench.sideBar.location" = "left"
    "workbench.panel.defaultLocation" = "bottom"
    "workbench.panel.opensMaximized" = "never"
    "workbench.secondarySideBar.defaultVisibility" = "visible"
    "git.enableSmartCommit" = $true
    "chatgpt.openOnStartup" = $true
    "files.exclude" = @{
        "**/__pycache__" = $true
        "**/.ruff_cache" = $true
    }
    "telemetry.telemetryLevel" = "off"
}
$plantUmlJar = Get-ChildItem -LiteralPath $extensionsDirectory -Filter "plantuml.jar" -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
if ($null -ne $plantUmlJar) {
    $settings["markdown-preview-enhanced.plantumlJarPath"] = $plantUmlJar.FullName
}
$settings | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $sharedSettingsPath -Encoding utf8
Copy-Item -LiteralPath $sharedSettingsPath -Destination (Join-Path $userDataDirectory "settings.json") -Force

$codeArguments = @(
    "--user-data-dir=$userDataDirectory",
    "--extensions-dir=$extensionsDirectory"
)

if ($InstallRecommendedExtensions) {
    foreach ($extension in @(
        "ms-python.python",
        "ms-vscode.powershell",
        "ms-toolsai.jupyter",
        "jebbs.plantuml",
        "mechatroner.rainbow-csv",
        "mhutchie.git-graph",
        "openai.chatgpt",
        "shd101wyy.markdown-preview-enhanced"
    )) {
        & $codeCli @codeArguments --install-extension $extension --force
        if ($LASTEXITCODE -ne 0) {
            throw "Could not install VS Code extension: $extension"
        }
    }
}

Write-Host "[OK] VS Code, Python, Git, and Codex are available in the shared developer environment."
Write-Host "[INFO] Shared VS Code settings and extensions: $runtimeRoot"
Write-Host "[INFO] Per-account VS Code sign-in state: $userDataDirectory"
Write-Host "[NEXT] Complete Codex sign-in with: & `"$codex`" login --device-auth"

if (-not $NoLaunch) {
    Start-Process -FilePath $codeExecutable -ArgumentList @($codeArguments + $projectRoot)
}
