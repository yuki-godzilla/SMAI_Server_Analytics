[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$analyticsPython = Join-Path $projectRoot "venv_SMAI_Analytics\Scripts\python.exe"
$compatibilityPython = "C:\Users\user\workspace\SMAI_Projects\Smart_Market_AI\venv_SMAI\Scripts\python.exe"
$webEntryPoint = Join-Path $projectRoot "analytics_web.py"

if (-not (Test-Path -LiteralPath $analyticsPython -PathType Leaf)) {
    if (Test-Path -LiteralPath $compatibilityPython -PathType Leaf) {
        $analyticsPython = $compatibilityPython
        Write-Host "[SMAI Analytics] Analytics venv was not found; using SMAI venv_SMAI for compatibility." -ForegroundColor Yellow
    } else {
        throw "Streamlit-enabled Python was not found. Run setup\setup.bat before starting the web console."
    }
}
if (-not (Test-Path -LiteralPath $webEntryPoint -PathType Leaf)) {
    throw "Analytics Web entry point was not found: $webEntryPoint"
}

$allowedNetworkVariables = @(
    "SMAI_TAILSCALE_HOSTNAME",
    "SMAI_MAIN_PORT",
    "SMAI_MAIN_APPLICATION_URL",
    "SMAI_ANALYTICS_PORT",
    "SMAI_ANALYTICS_SCHEME",
    "SMAI_SERVER_ANALYTICS_URL",
    "SMAI_LOCAL_ANALYTICS_URL"
)
$networkLines = & $analyticsPython -m smai_analytics.network --emit-batch
if ($LASTEXITCODE -ne 0) {
    throw "MagicDNS URL settings could not be loaded. Check config\network.json or SMAI_TAILSCALE_HOSTNAME."
}
foreach ($line in $networkLines) {
    if ($line -match '^set "([A-Z0-9_]+)=(.*)"$' -and $matches[1] -in $allowedNetworkVariables) {
        Set-Item -Path ("Env:{0}" -f $matches[1]) -Value $matches[2]
    }
}
if ([string]::IsNullOrWhiteSpace($env:SMAI_SERVER_ANALYTICS_URL) -or
    [string]::IsNullOrWhiteSpace($env:SMAI_ANALYTICS_PORT)) {
    throw "Validated Analytics URL settings were not returned."
}

Write-Host "============================================================" -ForegroundColor DarkCyan
Write-Host " SMAI Server Analytics | Web Operations Console" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor DarkCyan
Write-Host " Status : " -NoNewline -ForegroundColor DarkGray
Write-Host "starting" -ForegroundColor Yellow
Write-Host " Access : $env:SMAI_SERVER_ANALYTICS_URL" -ForegroundColor Cyan
Write-Host " Local  : $env:SMAI_LOCAL_ANALYTICS_URL" -ForegroundColor DarkCyan
Write-Host " Port   : TCP $env:SMAI_ANALYTICS_PORT (private network only)" -ForegroundColor Magenta
Write-Host ""

& $analyticsPython -m streamlit run $webEntryPoint `
    --server.address 0.0.0.0 `
    --server.port $env:SMAI_ANALYTICS_PORT `
    --server.headless true `
    --server.runOnSave false `
    --server.enableXsrfProtection true `
    --browser.gatherUsageStats false `
    --browser.serverAddress localhost

exit $LASTEXITCODE
