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
            return [pscustomobject]@{
                label = "healthy (HTTP $($response.StatusCode))"
                color = "Green"
            }
        }
        return [pscustomobject]@{
            label = "attention (HTTP $($response.StatusCode))"
            color = "Yellow"
        }
    } catch {
        return [pscustomobject]@{
            label = "unavailable ($($_.Exception.GetType().Name))"
            color = "Red"
        }
    }
}

try {
    $Host.UI.RawUI.WindowTitle = $target.title
    do {
        try { Clear-Host } catch {}
        $status = Get-ServiceStatus
        Write-Host "================================================" -ForegroundColor DarkCyan
        Write-Host " $($target.title)" -ForegroundColor Cyan
        Write-Host "================================================" -ForegroundColor DarkCyan
        Write-Host " Checked : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor DarkGray
        Write-Host " Health  : " -NoNewline -ForegroundColor DarkGray
        Write-Host $status.label -ForegroundColor $status.color
        Write-Host " Local   : $($target.page)" -ForegroundColor Cyan
        Write-Host " Port    : TCP $($target.port)" -ForegroundColor Magenta
        Write-Host ""
        Write-Host " This prompt monitors the existing server process; it does not start a duplicate instance." -ForegroundColor DarkGray
        if ($Watch) {
            Write-Host " Refresh : every $RefreshSeconds seconds " -NoNewline -ForegroundColor DarkGray
            Write-Host "(Ctrl+C stops updates)" -ForegroundColor Yellow
            Start-Sleep -Seconds $RefreshSeconds
        }
    } while ($Watch)
} finally {
    $mutex.ReleaseMutex()
    $mutex.Dispose()
}
