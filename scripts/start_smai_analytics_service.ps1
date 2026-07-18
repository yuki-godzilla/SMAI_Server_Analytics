[CmdletBinding()]
param(
    [ValidateRange(0, 120)]
    [int]$StartupDelaySeconds = 0
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$startScript = Join-Path $PSScriptRoot "run_analytics_web.ps1"
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

$mutex = [System.Threading.Mutex]::new($false, "Local\SMAI-Analytics-Service-Start")
$hasMutex = $false
try {
    $hasMutex = $mutex.WaitOne(0)
    if (-not $hasMutex) {
        Write-Host "[SMAI] Another Analytics start attempt is already in progress."
        exit 0
    }

    for ($attempt = 1; $attempt -le 3; $attempt++) {
        Write-Host "[SMAI] Starting Analytics Web Console in the background (attempt $attempt/3)."
        $startParameters = @{
            FilePath = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
            ArgumentList = @(
                "-NoProfile",
                "-WindowStyle", "Hidden",
                "-ExecutionPolicy", "Bypass",
                "-File", $startScript
            )
            WorkingDirectory = $projectRoot
            WindowStyle = "Hidden"
        }
        Start-Process @startParameters

        $deadline = (Get-Date).AddSeconds(45)
        do {
            Start-Sleep -Seconds 1
            if (Test-AnalyticsHealth) {
                Write-Host "[SMAI] Analytics Web Console is healthy on TCP 8502."
                exit 0
            }
        } while ((Get-Date) -lt $deadline)

        if ($attempt -lt 3) {
            Write-Warning "Analytics did not become healthy; retrying in 60 seconds."
            Start-Sleep -Seconds 60
        }
    }
    throw "Analytics Web Console did not become healthy after 3 start attempts."
} finally {
    if ($hasMutex) {
        $mutex.ReleaseMutex()
    }
    $mutex.Dispose()
}
