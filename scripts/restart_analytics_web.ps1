[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$webEntryPoint = Join-Path $projectRoot "analytics_web.py"
$startScript = Join-Path $PSScriptRoot "run_analytics_web.ps1"

if (-not (Test-Path -LiteralPath $webEntryPoint -PathType Leaf)) {
    throw "Analytics Web entry point was not found: $webEntryPoint"
}
if (-not (Test-Path -LiteralPath $startScript -PathType Leaf)) {
    throw "Analytics Web launcher was not found: $startScript"
}

$escapedEntryPoint = [regex]::Escape($webEntryPoint)
$processes = Get-CimInstance Win32_Process -ErrorAction Stop |
    Where-Object {
        $_.Name -like "python*.exe" -and
        [string]$_.CommandLine -match $escapedEntryPoint
    } |
    ForEach-Object { Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue } |
    Where-Object { $null -ne $_ } |
    Sort-Object Id -Unique

foreach ($process in $processes) {
    $liveProcess = Get-Process -Id $process.Id -ErrorAction SilentlyContinue
    if ($null -ne $liveProcess) {
        Stop-Process -Id $process.Id -Force -ErrorAction Stop
        Write-Host "[SMAI] Stopped Analytics Web process: $($process.Id)"
    }
}

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
Write-Host "[SMAI] Analytics Web restart requested."
