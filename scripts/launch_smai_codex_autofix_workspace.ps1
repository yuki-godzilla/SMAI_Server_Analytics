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

$userDataDirectory = Join-Path $runtimeRoot "vscode-user-data"
$extensionsDirectory = Join-Path $runtimeRoot "vscode-extensions"
New-Item -ItemType Directory -Path $userDataDirectory, $extensionsDirectory -Force | Out-Null

$settings = @{
    "python.defaultInterpreterPath" = $python
    "python.terminal.activateEnvironment" = $false
    "terminal.integrated.defaultProfile.windows" = "PowerShell"
    "files.exclude" = @{
        "**/__pycache__" = $true
        "**/.ruff_cache" = $true
    }
    "telemetry.telemetryLevel" = "off"
} | ConvertTo-Json -Depth 4
Set-Content -LiteralPath (Join-Path $userDataDirectory "settings.json") -Value $settings -Encoding utf8

$codeArguments = @(
    "--user-data-dir=$userDataDirectory",
    "--extensions-dir=$extensionsDirectory"
)

if ($InstallRecommendedExtensions) {
    foreach ($extension in @("ms-python.python", "ms-vscode.powershell")) {
        & $codeCli @codeArguments --install-extension $extension --force
        if ($LASTEXITCODE -ne 0) {
            throw "Could not install VS Code extension: $extension"
        }
    }
}

Write-Host "[OK] VS Code, Python, Git, and Codex are available in the shared developer environment."
Write-Host "[INFO] VS Code settings and extensions: $runtimeRoot"
Write-Host "[NEXT] Complete Codex sign-in with: & `"$codex`" login --device-auth"

if (-not $NoLaunch) {
    Start-Process -FilePath $codeExecutable -ArgumentList @($codeArguments + $projectRoot)
}
