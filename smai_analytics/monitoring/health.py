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

from . import data_freshness, host_health, telemetry

PROJECT_ROOT = Path(os.environ.get("SMAI_PROJECT_ROOT", r"C:\Users\user\workspace\SMAI_Projects\Smart_Market_AI"))
RUNTIME_ROOT = Path(os.environ.get("SMAI_RUNTIME_ROOT", r"C:\Users\user\workspace\SMAI_Projects\SMAI_Server_Runtime"))
SNAPSHOT_PATH = PROJECT_ROOT / "data/ops/server_ops/health_snapshot.json"
RUNTIME_LIFECYCLE_PATH = PROJECT_ROOT / "data/ops/server_ops/runtime_lifecycle.json"
LIFECYCLE_GRACE_SECONDS = 180.0
EXPECTED_TRANSITION_PHASES = {"STARTING": "starting", "STOPPING": "stopping"}
MAIN_ENTRYPOINT_CHECKS = {"TCP 8501", "Streamlit health"}


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


def _overall_status(checks: list[Check]) -> str:
    """Separate service continuity from the data-quality warning channel."""

    if any(
        check.status in {"failed", "critical"} and check.level in {"L1", "L3"}
        for check in checks
    ):
        return "critical"
    if any(check.status != "ok" for check in checks):
        return "degraded"
    return "healthy"


def _read_runtime_lifecycle(path: Path = RUNTIME_LIFECYCLE_PATH) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


def _lifecycle_age_seconds(lifecycle: dict[str, object], *, now: datetime | None = None) -> float | None:
    raw = lifecycle.get("updated_at")
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    current = now or datetime.now(UTC)
    return max(0.0, (current - parsed.astimezone(UTC)).total_seconds())


def _expected_transition_status(
    checks: list[Check],
    lifecycle: dict[str, object],
    *,
    now: datetime | None = None,
) -> str | None:
    phase = str(lifecycle.get("phase", "")).upper()
    mapped = EXPECTED_TRANSITION_PHASES.get(phase)
    if mapped is None:
        return None
    age = _lifecycle_age_seconds(lifecycle, now=now)
    if age is None or age > LIFECYCLE_GRACE_SECONDS:
        return None

    continuity_failures = [
        check
        for check in checks
        if check.status in {"failed", "critical"} and check.level in {"L1", "L3"}
    ]
    if not continuity_failures:
        return None
    if all(check.level == "L1" and check.name in MAIN_ENTRYPOINT_CHECKS for check in continuity_failures):
        return mapped
    return None


def collect(
    *,
    host_checks: list[dict[str, object]] | None = None,
    freshness_checks: list[dict[str, object]] | None = None,
    runtime_lifecycle: dict[str, object] | None = None,
) -> dict[str, object]:
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
    for item in freshness_checks if freshness_checks is not None else data_freshness.collect_checks(PROJECT_ROOT):
        checks.append(
            Check(
                str(item["name"]),
                str(item["level"]),
                str(item["status"]),
                str(item["detail"]),
            )
        )
    for item in host_checks if host_checks is not None else host_health.collect_checks():
        try:
            checks.append(
                Check(
                    str(item["name"]),
                    str(item["level"]),
                    str(item["status"]),
                    str(item["detail"]),
                    int(item["latency_ms"]) if isinstance(item.get("latency_ms"), int) else None,
                )
            )
        except (KeyError, TypeError, ValueError):
            checks.append(Check("Windows host telemetry", "L3", "unknown", "invalid host telemetry", None))

    lifecycle = runtime_lifecycle if runtime_lifecycle is not None else _read_runtime_lifecycle()
    overall = _overall_status(checks)
    transition_status = _expected_transition_status(checks, lifecycle)
    if overall == "critical" and transition_status is not None:
        overall = transition_status

    return {
        "checked_at": datetime.now(UTC).isoformat(),
        "overall": overall,
        "runtime_phase": str(lifecycle.get("phase", "UNKNOWN")).upper(),
        "runtime_lifecycle": lifecycle,
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
