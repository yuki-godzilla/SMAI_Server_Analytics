[CmdletBinding()]
param(
    [ValidateRange(0, 120)]
    [int]$StartupDelaySeconds = 0
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$startScript = Join-Path $projectRoot "run_analytics_web.bat"
if (-not (Test-Path -LiteralPath $startScript -PathType Leaf)) {
    throw "Analytics launcher was not found: $startScript"
}
if ($StartupDelaySeconds -gt 0) {
    Start-Sleep -Seconds $StartupDelaySeconds
}

function Test-AnalyticsHealth {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8502/_stcore/health" -TimeoutSec 3
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 400
    } catch {
        return $false
    }
}

if (Test-AnalyticsHealth) {
    Write-Host "[SMAI] Analytics Web Console is already healthy on TCP 8502."
    exit 0
}

if (Get-NetTCPConnection -State Listen -LocalPort 8502 -ErrorAction SilentlyContinue) {
    throw "TCP 8502 is already in use, but the SMAI Analytics health endpoint is unavailable."
}

for ($attempt = 1; $attempt -le 3; $attempt++) {
    Write-Host "[SMAI] Starting Analytics Web Console (attempt $attempt/3)."
    & $startScript
    $exitCode = $LASTEXITCODE
    if ($exitCode -eq 0) {
        exit 0
    }
    if ($attempt -lt 3) {
        Start-Sleep -Seconds 60
    }
}
exit $exitCode
