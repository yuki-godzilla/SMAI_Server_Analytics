[CmdletBinding()]
param(
    [ValidateRange(0, 120)]
    [int]$StartupDelaySeconds = 5,
    [ValidateRange(10, 300)]
    [int]$WaitSeconds = 180
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$logDir = Join-Path $projectRoot "logs"
$logFile = Join-Path $logDir "workspace.log"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

function Write-WorkspaceLog {
    param([string]$Message)
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -LiteralPath $logFile -Value "$stamp $Message" -Encoding UTF8
}

if ($StartupDelaySeconds -gt 0) {
    Start-Sleep -Seconds $StartupDelaySeconds
}

$targets = @(
    [pscustomobject]@{
        Name = "SMAI Main Application"
        Health = "http://127.0.0.1:8501/_stcore/health"
        Page = "http://localhost:8501"
        WindowTitle = "Smart Market AI*"
    },
    [pscustomobject]@{
        Name = "SMAI Analytics"
        Health = "http://127.0.0.1:8502/_stcore/health"
        Page = "http://localhost:8502"
        WindowTitle = "SMAI Analytics*"
    }
)

function Get-ChromeExecutable {
    $candidates = @(
        (Join-Path $env:ProgramFiles "Google\Chrome\Application\chrome.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Google\Chrome\Application\chrome.exe"),
        (Join-Path $env:LOCALAPPDATA "Google\Chrome\Application\chrome.exe")
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) }
    return $candidates | Select-Object -First 1
}

function Test-WindowAlreadyOpen {
    param([string]$TitlePattern)
    return $null -ne (Get-Process chrome -ErrorAction SilentlyContinue |
        Where-Object { $_.MainWindowHandle -ne 0 -and $_.MainWindowTitle -like $TitlePattern } |
        Select-Object -First 1)
}

$chrome = Get-ChromeExecutable
$deadline = (Get-Date).AddSeconds($WaitSeconds)
$ready = @{}

do {
    foreach ($target in $targets) {
        if ($ready[$target.Name]) { continue }
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $target.Health -TimeoutSec 3
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) {
                $ready[$target.Name] = $true
                Write-WorkspaceLog "READY $($target.Name) $($target.Health)"
            }
        } catch {}
    }
    if ($ready.Count -eq $targets.Count -or (Get-Date) -ge $deadline) { break }
    Start-Sleep -Seconds 3
} while ($true)

foreach ($target in $targets) {
    if (-not $ready[$target.Name]) {
        Write-WorkspaceLog "TIMEOUT $($target.Name) did not become ready within ${WaitSeconds}s."
        continue
    }

    if (Test-WindowAlreadyOpen -TitlePattern $target.WindowTitle) {
        Write-WorkspaceLog "REUSE Existing window: $($target.Name)"
        continue
    }

    if ($chrome) {
        Start-Process -FilePath $chrome -ArgumentList @("--app=$($target.Page)")
        Write-WorkspaceLog "OPEN App window: $($target.Name)"
    } else {
        Start-Process $target.Page
        Write-WorkspaceLog "OPEN Default browser fallback: $($target.Name)"
    }
}
