[CmdletBinding()]
param(
    [ValidateRange(0, 120)]
    [int]$StartupDelaySeconds = 0
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$startScript = Join-Path $PSScriptRoot "run_analytics_web.ps1"
$hostMonitorScript = Join-Path $PSScriptRoot "run_smai_host_monitor.ps1"
if (-not (Test-Path -LiteralPath $startScript -PathType Leaf)) {
    throw "Analytics launcher was not found: $startScript"
}
if (-not (Test-Path -LiteralPath $hostMonitorScript -PathType Leaf)) {
    throw "Host monitor launcher was not found: $hostMonitorScript"
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

function Test-SmaiApplicationHealth {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8501/_stcore/health" -TimeoutSec 3
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 400
    } catch {
        return $false
    }
}

function Update-StartupHealthSnapshot {
    # Do not let a probe made while SMAI was still binding its port remain on the
    # dashboard until the five-minute monitor interval elapses. This normal
    # monitor run retains fail-closed behavior if SMAI never becomes ready.
    & $hostMonitorScript | Out-Null
    return $LASTEXITCODE
}

function Sync-HealthAfterSmaiStartup {
    $deadline = (Get-Date).AddSeconds(180)
    do {
        if (Test-SmaiApplicationHealth) {
            $monitorExit = Update-StartupHealthSnapshot
            if ($monitorExit -eq 0) {
                Write-Host "[SMAI] Recorded a fresh healthy snapshot after SMAI startup."
            } else {
                Write-Warning "[SMAI] SMAI responded, but the fresh health snapshot still needs attention."
            }
            return
        }
        Start-Sleep -Seconds 5
    } while ((Get-Date) -lt $deadline)

    # A main service that truly did not start remains fail-closed and visible.
    Update-StartupHealthSnapshot | Out-Null
    Write-Warning "[SMAI] SMAI did not become healthy within 180 seconds; recorded the current health result."
}

if (Test-AnalyticsHealth) {
    Write-Host "[SMAI] Analytics Web Console is already healthy on TCP 8502."
    Sync-HealthAfterSmaiStartup
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
                Sync-HealthAfterSmaiStartup
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
