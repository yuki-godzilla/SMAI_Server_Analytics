from __future__ import annotations

import json
import os
import shutil
import socket
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from . import telemetry

PROJECT_ROOT = Path(os.environ.get("SMAI_PROJECT_ROOT", r"C:\Users\user\workspace\SMAI_Projects\Smart_Market_AI"))
RUNTIME_ROOT = Path(os.environ.get("SMAI_RUNTIME_ROOT", r"C:\Users\user\workspace\SMAI_Projects\SMAI_Server_Runtime"))
SNAPSHOT_PATH = PROJECT_ROOT / "data/ops/server_ops/health_snapshot.json"


@dataclass(frozen=True)
class Check:
    name: str
    level: str
    status: str
    detail: str
    latency_ms: int | None = None


def _elapsed_ms(started_at: float) -> int:
    return max(0, round((time.monotonic() - started_at) * 1000))


def _url_ok(url: str, expected: bytes | None = None) -> tuple[bool, str, int]:
    started_at = time.monotonic()
    try:
        with urlopen(url, timeout=2.0) as response:
            body = response.read(4096)
            ok = 200 <= response.status < 400 and (expected is None or body.strip().lower() == expected)
            return ok, f"HTTP {response.status}" if ok else "unexpected response", _elapsed_ms(started_at)
    except (OSError, URLError) as exc:
        return False, type(exc).__name__, _elapsed_ms(started_at)


def _storage_metrics() -> list[dict[str, object]]:
    """Collect volume headroom without retaining local paths or user data."""

    metrics: list[dict[str, object]] = []
    for name, path in (("SMAI data", PROJECT_ROOT), ("Runtime", RUNTIME_ROOT)):
        try:
            usage = shutil.disk_usage(path if path.exists() else path.parent)
        except OSError as exc:
            metrics.append({"name": name, "status": "unknown", "detail": type(exc).__name__})
            continue
        free_percent = round(usage.free * 100 / usage.total, 1) if usage.total else 0.0
        metrics.append(
            {
                "name": name,
                "status": "ok",
                "total_bytes": usage.total,
                "used_bytes": usage.used,
                "free_bytes": usage.free,
                "free_percent": free_percent,
            }
        )
    return metrics


def collect() -> dict[str, object]:
    checks: list[Check] = []
    started_at = time.monotonic()
    try:
        with socket.create_connection(("127.0.0.1", 8501), timeout=1):
            checks.append(Check("TCP 8501", "L1", "ok", "listener accepting connections", _elapsed_ms(started_at)))
    except OSError as exc:
        checks.append(Check("TCP 8501", "L1", "failed", type(exc).__name__, _elapsed_ms(started_at)))
    for name, url, expected, level in (
        ("Streamlit health", "http://127.0.0.1:8501/_stcore/health", b"ok", "L1"),
        ("Streamlit page", "http://127.0.0.1:8501/", None, "L2"),
    ):
        ok, detail, latency_ms = _url_ok(url, expected)
        checks.append(Check(name, level, "ok" if ok else "failed", detail, latency_ms))
    for name, path in (("server ops state", PROJECT_ROOT / "data/ops/server_ops"), ("user data", PROJECT_ROOT / "data/user")):
        started_at = time.monotonic()
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".health_probe.tmp"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            checks.append(Check(name, "L3", "ok", "read/write available", _elapsed_ms(started_at)))
        except OSError as exc:
            checks.append(Check(name, "L3", "failed", type(exc).__name__, _elapsed_ms(started_at)))
    overall = "critical" if any(c.level == "L1" and c.status == "failed" for c in checks) else "degraded" if any(c.status == "failed" for c in checks) else "healthy"
    return {
        "checked_at": datetime.now(UTC).isoformat(),
        "overall": overall,
        "checks": [asdict(c) for c in checks],
        "storage": _storage_metrics(),
    }


def main() -> int:
    payload = collect()
    payload["telemetry"] = telemetry.record_health_snapshot(payload, RUNTIME_ROOT)
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = SNAPSHOT_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(SNAPSHOT_PATH)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["overall"] != "critical" else 1


if __name__ == "__main__":
    raise SystemExit(main())
