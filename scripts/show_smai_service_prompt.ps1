[CmdletBinding()]
param(
    [ValidateSet("Main", "Analytics")]
    [string]$Service,
    [ValidateRange(5, 300)]
    [int]$RefreshSeconds = 30,
    [switch]$Watch
)

$ErrorActionPreference = "Stop"
$services = @{
    Main = @{
        title = "SMAI Main Application Prompt"
        health = "http://127.0.0.1:8501/_stcore/health"
        page = "http://localhost:8501"
        port = 8501
    }
    Analytics = @{
        title = "SMAI Analytics Prompt"
        health = "http://127.0.0.1:8502/_stcore/health"
        page = "http://localhost:8502"
        port = 8502
    }
}

$target = $services[$Service]
$mutexCreated = $false
$mutex = [System.Threading.Mutex]::new($true, "Local\SMAI-$Service-Operations-Prompt", [ref]$mutexCreated)
if (-not $mutexCreated) {
    Write-Host "[SMAI] $Service prompt is already open in this Windows session."
    exit 0
}

function Get-ServiceStatus {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $target.health -TimeoutSec 3
        if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) {
            return "healthy (HTTP $($response.StatusCode))"
        }
        return "attention (HTTP $($response.StatusCode))"
    } catch {
        return "unavailable ($($_.Exception.GetType().Name))"
    }
}

try {
    $Host.UI.RawUI.WindowTitle = $target.title
    do {
        try { Clear-Host } catch {}
        Write-Host "=============================================="
        Write-Host " $($target.title)"
        Write-Host "=============================================="
        Write-Host "Checked : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
        Write-Host "Health  : $(Get-ServiceStatus)"
        Write-Host "Local   : $($target.page)"
        Write-Host "Port    : TCP $($target.port)"
        Write-Host ""
        Write-Host "This prompt monitors the existing server process; it does not start a duplicate instance."
        if ($Watch) {
            Write-Host "Refresh : every $RefreshSeconds seconds (Ctrl+C stops updates)"
            Start-Sleep -Seconds $RefreshSeconds
        }
    } while ($Watch)
} finally {
    $mutex.ReleaseMutex()
    $mutex.Dispose()
}
