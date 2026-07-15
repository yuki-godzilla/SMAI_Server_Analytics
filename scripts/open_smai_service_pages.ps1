[CmdletBinding()]
param(
    [ValidateRange(0, 120)]
    [int]$StartupDelaySeconds = 10,
    [ValidateRange(10, 300)]
    [int]$WaitSeconds = 180
)

$ErrorActionPreference = "Stop"
if ($StartupDelaySeconds -gt 0) {
    Start-Sleep -Seconds $StartupDelaySeconds
}

$targets = @(
    @{ name = "SMAI Main Application"; health = "http://127.0.0.1:8501/_stcore/health"; page = "http://localhost:8501" },
    @{ name = "SMAI Analytics"; health = "http://127.0.0.1:8502/_stcore/health"; page = "http://localhost:8502" }
)
$deadline = (Get-Date).AddSeconds($WaitSeconds)
$ready = @{}

do {
    foreach ($target in $targets) {
        if ($ready[$target.name]) { continue }
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $target.health -TimeoutSec 3
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) {
                $ready[$target.name] = $true
            }
        } catch {}
    }
    if ($ready.Count -eq $targets.Count -or (Get-Date) -ge $deadline) { break }
    Start-Sleep -Seconds 5
} while ($true)

foreach ($target in $targets) {
    if ($ready[$target.name]) {
        Start-Process $target.page
        Write-Host "[OK] Opened: $($target.name)"
    } else {
        Write-Warning "$($target.name) did not become healthy within $WaitSeconds seconds; no browser page was opened."
    }
}
