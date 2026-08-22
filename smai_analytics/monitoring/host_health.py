"""Small, privacy-safe Windows host checks for the SMAI health snapshot."""

from __future__ import annotations

import json
import subprocess
from typing import Any, Callable

PowerShellRunner = Callable[..., subprocess.CompletedProcess[str]]

_HOST_QUERY = r"""
$ErrorActionPreference = 'Stop'
$disks = @()
try {
  $disks = @(Get-PhysicalDisk | ForEach-Object {
    [pscustomobject]@{ health = [string]$_.HealthStatus; operational = [string]$_.OperationalStatus }
  })
} catch {}
$tailscale = $null
try { $tailscale = Get-NetAdapter -IncludeHidden | Where-Object { $_.Name -eq 'Tailscale' } | Select-Object -First 1 } catch {}
$memoryFreePercent = $null
try {
  $os = Get-CimInstance Win32_OperatingSystem
  if ($os.TotalVisibleMemorySize -gt 0) {
    $memoryFreePercent = [math]::Round(($os.FreePhysicalMemory * 100.0) / $os.TotalVisibleMemorySize, 1)
  }
} catch {}
$cpuPercent = $null
try {
  $cpu = @(Get-CimInstance Win32_Processor | Where-Object { $null -ne $_.LoadPercentage })
  if ($cpu.Count -gt 0) { $cpuPercent = [math]::Round((($cpu | Measure-Object -Property LoadPercentage -Average).Average), 1) }
} catch {}
if ($null -eq $cpuPercent) {
  try {
    $sample = Get-Counter '\Processor(_Total)\% Processor Time' -ErrorAction Stop |
      Select-Object -ExpandProperty CounterSamples |
      Select-Object -First 1
    if ($null -ne $sample -and $null -ne $sample.CookedValue) {
      $cpuPercent = [math]::Round([double]$sample.CookedValue, 1)
    }
  } catch {}
}
$unexpectedShutdowns = 0
try {
  $unexpectedShutdowns = @(
    Get-WinEvent -FilterHashtable @{ LogName = 'System'; Id = 41, 6008; StartTime = (Get-Date).AddHours(-24) } -ErrorAction SilentlyContinue
  ).Count
} catch {}
$gpus = @()
try {
  $nvidia = Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue
  if ($nvidia) {
    $gpuRows = & $nvidia.Source --query-gpu=name,temperature.gpu,fan.speed,power.draw,power.limit,utilization.gpu --format=csv,noheader,nounits 2>$null
    foreach ($row in @($gpuRows)) {
      $parts = ([string]$row -split ',\s*')
      if ($parts.Count -ge 6) {
        $temperature = 0.0
        $fan = 0.0
        $power = 0.0
        $limit = 0.0
        $utilization = 0.0
        if ([double]::TryParse($parts[1], [Globalization.NumberStyles]::Float, [Globalization.CultureInfo]::InvariantCulture, [ref]$temperature)) {
          [void][double]::TryParse($parts[2], [Globalization.NumberStyles]::Float, [Globalization.CultureInfo]::InvariantCulture, [ref]$fan)
          [void][double]::TryParse($parts[3], [Globalization.NumberStyles]::Float, [Globalization.CultureInfo]::InvariantCulture, [ref]$power)
          [void][double]::TryParse($parts[4], [Globalization.NumberStyles]::Float, [Globalization.CultureInfo]::InvariantCulture, [ref]$limit)
          [void][double]::TryParse($parts[5], [Globalization.NumberStyles]::Float, [Globalization.CultureInfo]::InvariantCulture, [ref]$utilization)
          $gpus += [pscustomobject]@{
            temperature_c = [math]::Round($temperature, 1)
            fan_percent = [math]::Round($fan, 1)
            power_draw_w = [math]::Round($power, 1)
            power_limit_w = [math]::Round($limit, 1)
            utilization_percent = [math]::Round($utilization, 1)
          }
        }
      }
    }
  }
} catch {}
[pscustomobject]@{
  tailscale_status = if ($tailscale) { [string]$tailscale.Status } else { 'missing' }
  disks = $disks
  memory_free_percent = $memoryFreePercent
  cpu_percent = $cpuPercent
  unexpected_shutdown_events = $unexpectedShutdowns
  gpus = $gpus
} | ConvertTo-Json -Compress -Depth 4
"""


def _run_host_query(
    *, runner: PowerShellRunner = subprocess.run
) -> dict[str, object] | None:
    """Return only bounded machine-health values, never paths or user details."""

    try:
        result = runner(
            ["powershell.exe", "-NoProfile", "-Command", _HOST_QUERY],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    try:
        value: Any = json.loads(result.stdout or "")
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _status(value: object) -> str:
    return str(value or "").strip().casefold()


def collect_checks(*, runner: PowerShellRunner = subprocess.run) -> list[dict[str, object]]:
    """Return L2/L3 checks without making host telemetry a restart trigger."""

    payload = _run_host_query(runner=runner)
    if payload is None:
        return [
            {
                "name": "Windows host telemetry",
                "level": "L3",
                "status": "unknown",
                "detail": "host telemetry unavailable",
                "latency_ms": None,
            }
        ]

    checks: list[dict[str, object]] = []
    tailscale = _status(payload.get("tailscale_status"))
    checks.append(
        {
            "name": "Tailscale adapter",
            "level": "L2",
            "status": "ok" if tailscale == "up" else "failed",
            "detail": "adapter up" if tailscale == "up" else "adapter unavailable",
            "latency_ms": None,
        }
    )

    gpus = payload.get("gpus")
    gpu_values = [item for item in gpus if isinstance(item, dict)] if isinstance(gpus, list) else []
    if gpu_values:
        temperatures = [float(item["temperature_c"]) for item in gpu_values if isinstance(item.get("temperature_c"), (int, float))]
        fans = [float(item["fan_percent"]) for item in gpu_values if isinstance(item.get("fan_percent"), (int, float))]
        powers = [float(item["power_draw_w"]) for item in gpu_values if isinstance(item.get("power_draw_w"), (int, float))]
        if temperatures:
            maximum = max(temperatures)
            status = "failed" if maximum >= 90 else "degraded" if maximum >= 85 else "ok"
            detail = f"GPU temperature {maximum:.0f}°C"
            if fans:
                detail += f", fan {max(fans):.0f}%"
            if powers:
                detail += f", power {max(powers):.0f}W"
            checks.append({"name": "GPU thermal", "level": "L3", "status": status, "detail": detail, "latency_ms": None})

    disks = payload.get("disks")
    disk_values = [item for item in disks if isinstance(item, dict)] if isinstance(disks, list) else []
    if not disk_values:
        disk_status, disk_detail = "unknown", "physical disk status unavailable"
    elif all(
        _status(item.get("health")) == "healthy" and _status(item.get("operational")) == "ok"
        for item in disk_values
    ):
        disk_status, disk_detail = "ok", "physical disks healthy"
    else:
        disk_status, disk_detail = "failed", "physical disk requires attention"
    checks.append(
        {
            "name": "Physical disk health",
            "level": "L3",
            "status": disk_status,
            "detail": disk_detail,
            "latency_ms": None,
        }
    )

    free_memory = payload.get("memory_free_percent")
    if isinstance(free_memory, (int, float)):
        memory_status = "ok" if free_memory >= 10 else "failed"
        memory_detail = f"free memory {free_memory:.1f}%"
    else:
        memory_status, memory_detail = "unknown", "memory availability unavailable"
    checks.append(
        {
            "name": "Host memory",
            "level": "L3",
            "status": memory_status,
            "detail": memory_detail,
            "latency_ms": None,
        }
    )

    cpu = payload.get("cpu_percent")
    if isinstance(cpu, (int, float)):
        cpu_status = "ok" if cpu < 90 else "degraded"
        cpu_detail = f"processor load {cpu:.1f}%"
    else:
        cpu_status, cpu_detail = "unknown", "processor load unavailable"
    checks.append(
        {
            "name": "Host processor",
            "level": "L3",
            "status": cpu_status,
            "detail": cpu_detail,
            "latency_ms": None,
        }
    )

    events = payload.get("unexpected_shutdown_events")
    if isinstance(events, int) and events >= 0:
        event_status = "ok" if events == 0 else "degraded"
        event_detail = "no unexpected shutdown in 24h" if events == 0 else f"unexpected shutdown events in 24h: {events}"
    else:
        event_status, event_detail = "unknown", "shutdown event history unavailable"
    checks.append(
        {
            "name": "Unexpected shutdown events",
            "level": "L3",
            "status": event_status,
            "detail": event_detail,
            "latency_ms": None,
        }
    )
    return checks
