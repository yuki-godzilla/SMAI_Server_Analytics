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

function Get-ChromeExecutable {
    $candidates = @(
        (Join-Path $env:ProgramFiles "Google\Chrome\Application\chrome.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Google\Chrome\Application\chrome.exe"),
        (Join-Path $env:LOCALAPPDATA "Google\Chrome\Application\chrome.exe")
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) }
    return $candidates | Select-Object -First 1
}

$chrome = Get-ChromeExecutable
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
        if ($chrome) {
            # A separate Chrome window is required so Main and Analytics can
            # occupy their own half of the secondary display.
            Start-Process -FilePath $chrome -ArgumentList @("--new-window", $target.page)
        } else {
            Write-Warning "Google Chrome was not found; opening $($target.name) in the default browser instead."
            Start-Process $target.page
        }
        Write-Host "[OK] Opened: $($target.name)"
    } else {
        Write-Warning "$($target.name) did not become healthy within $WaitSeconds seconds; no browser page was opened."
    }
}
