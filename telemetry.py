"""Durable, privacy-safe health telemetry for the local Analytics console.

The dashboard refreshes every few seconds, but its visual history must survive a
dashboard restart.  This module retains the current five-minute aggregate in a
small atomic state file and appends completed aggregates as compact JSONL.
Raw health snapshots are partitioned by day for short-term investigation; the
retention job owns their lifetime.
"""

from __future__ import annotations

import json
import math
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Mapping

SCHEMA_VERSION = 1
BUCKET_SECONDS = 5 * 60
HEALTH_LOG_DIRECTORY = "health"
METRICS_DIRECTORY = "metrics"
HEALTH_ROLLUP_DIRECTORY = "health"
HEALTH_ROLLUP_STATE = "health_rollup_state.json"
GOOD_STATUSES = {"ok", "healthy", "active", "running", "ready"}
DEGRADED_STATUSES = {"degraded", "stale", "cancelled", "disabled", "queued"}
CRITICAL_STATUSES = {"failed", "error", "critical"}


def parse_timestamp(value: object) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def bucket_start(value: datetime) -> datetime:
    seconds = int(value.astimezone(UTC).timestamp())
    return datetime.fromtimestamp(seconds - seconds % BUCKET_SECONDS, tz=UTC)


def _state_path(runtime_root: Path) -> Path:
    return runtime_root / METRICS_DIRECTORY / HEALTH_ROLLUP_STATE


def _rollup_path(runtime_root: Path, start: datetime) -> Path:
    return runtime_root / METRICS_DIRECTORY / HEALTH_ROLLUP_DIRECTORY / f"{start:%Y-%m-%d}.jsonl"


def _raw_path(runtime_root: Path, checked_at: datetime) -> Path:
    return runtime_root / "logs" / HEALTH_LOG_DIRECTORY / f"{checked_at:%Y-%m-%d}.jsonl"


def _atomic_write(path: Path, value: Mapping[str, object]) -> bool:
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(path)
        return True
    except OSError:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        return False


def _read_json(path: Path) -> dict[str, object] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def _append_jsonl(path: Path, value: Mapping[str, object]) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")
        return True
    except OSError:
        return False


def _new_aggregate(start: datetime) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "bucket_start": start.isoformat(),
        "sample_count": 0,
        "overall": {},
        "levels": {},
        "latency_samples_ms": {},
        "storage": [],
    }


def _increment(counts: dict[str, object], status: str) -> None:
    counts[status] = int(counts.get(status, 0)) + 1


def _normal_status(value: object) -> str:
    status = str(value or "unknown").strip().casefold()
    return status or "unknown"


def _record_snapshot(aggregate: dict[str, object], snapshot: Mapping[str, object]) -> None:
    aggregate["sample_count"] = int(aggregate.get("sample_count", 0)) + 1
    overall = aggregate.setdefault("overall", {})
    if isinstance(overall, dict):
        _increment(overall, _normal_status(snapshot.get("overall")))

    levels = aggregate.setdefault("levels", {})
    checks = snapshot.get("checks")
    if isinstance(levels, dict) and isinstance(checks, list):
        for item in checks:
            if not isinstance(item, dict):
                continue
            level = str(item.get("level") or "unknown").upper()
            level_counts = levels.setdefault(level, {})
            if isinstance(level_counts, dict):
                _increment(level_counts, _normal_status(item.get("status")))
            latency = item.get("latency_ms")
            name = str(item.get("name") or "unknown")[:120]
            if isinstance(latency, int) and latency >= 0:
                latency_samples = aggregate.setdefault("latency_samples_ms", {})
                if isinstance(latency_samples, dict):
                    values = latency_samples.setdefault(name, [])
                    if isinstance(values, list) and len(values) < 120:
                        values.append(latency)

    storage = snapshot.get("storage")
    if isinstance(storage, list):
        # Storage is a current measurement rather than a cumulative sum.  Keep
        # only the newest safe, bounded reading for the bucket.
        aggregate["storage"] = [item for item in storage if isinstance(item, dict)][:8]


def _percentile(values: list[int], percentile: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(percentile * len(ordered)) - 1))
    return ordered[index]


def _finalize(aggregate: Mapping[str, object]) -> dict[str, object] | None:
    start = parse_timestamp(aggregate.get("bucket_start"))
    if start is None:
        return None
    levels = aggregate.get("levels")
    overall = aggregate.get("overall")
    if not isinstance(levels, dict) or not isinstance(overall, dict):
        return None
    latency_summary: dict[str, dict[str, int]] = {}
    raw_latency = aggregate.get("latency_samples_ms")
    if isinstance(raw_latency, dict):
        for name, raw_values in raw_latency.items():
            values = [int(item) for item in raw_values if isinstance(item, int) and item >= 0] if isinstance(raw_values, list) else []
            if values:
                latency_summary[str(name)[:120]] = {
                    "count": len(values),
                    "avg_ms": round(sum(values) / len(values)),
                    "p95_ms": _percentile(values, 0.95) or 0,
                    "max_ms": max(values),
                }
    else:
        persisted_latency = aggregate.get("latency_ms")
        if isinstance(persisted_latency, dict):
            for name, metric in persisted_latency.items():
                if not isinstance(metric, dict):
                    continue
                values = {
                    key: int(metric[key])
                    for key in ("count", "avg_ms", "p95_ms", "max_ms")
                    if isinstance(metric.get(key), int) and int(metric[key]) >= 0
                }
                if {"count", "avg_ms", "p95_ms", "max_ms"}.issubset(values):
                    latency_summary[str(name)[:120]] = values
    storage = aggregate.get("storage")
    return {
        "schema_version": SCHEMA_VERSION,
        "bucket_start": bucket_start(start).isoformat(),
        "sample_count": max(0, int(aggregate.get("sample_count", 0))),
        "overall": {str(key): int(value) for key, value in overall.items() if isinstance(value, int)},
        "levels": {
            str(level): {str(status): int(count) for status, count in counts.items() if isinstance(count, int)}
            for level, counts in levels.items()
            if isinstance(counts, dict)
        },
        "latency_ms": latency_summary,
        "storage": [item for item in storage if isinstance(item, dict)][:8] if isinstance(storage, list) else [],
    }


def _valid_aggregate(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        return None
    if parse_timestamp(value.get("bucket_start")) is None:
        return None
    return value


def record_health_snapshot(snapshot: Mapping[str, object], runtime_root: Path) -> dict[str, object]:
    """Persist a raw snapshot and five-minute aggregate without user data.

    The function returns an explicit status so a caller can expose telemetry
    storage failures without pretending that missing history is healthy.
    """

    checked_at = parse_timestamp(snapshot.get("checked_at"))
    if checked_at is None:
        return {"status": "unknown", "detail": "health timestamp unavailable"}
    raw_written = _append_jsonl(_raw_path(runtime_root, checked_at), dict(snapshot))
    state_path = _state_path(runtime_root)
    existing = _valid_aggregate(_read_json(state_path))
    current_start = bucket_start(checked_at)
    completed = True
    if existing is not None and bucket_start(parse_timestamp(existing["bucket_start"]) or current_start) != current_start:
        finalized = _finalize(existing)
        completed = finalized is not None and _append_jsonl(
            _rollup_path(runtime_root, parse_timestamp(existing["bucket_start"]) or current_start),
            finalized or {},
        )
        existing = None
    aggregate = existing if existing is not None else _new_aggregate(current_start)
    _record_snapshot(aggregate, snapshot)
    state_written = _atomic_write(state_path, aggregate)
    if raw_written and completed and state_written:
        return {"status": "healthy", "detail": "local telemetry recorded"}
    return {"status": "unknown", "detail": "telemetry storage unavailable"}


def status_from_counts(counts: object) -> str:
    """Return the worst observed status while leaving absent evidence unknown."""

    if not isinstance(counts, dict) or not counts:
        return "unknown"
    keys = {_normal_status(key) for key, value in counts.items() if isinstance(value, int) and value > 0}
    if keys & CRITICAL_STATUSES:
        return "critical"
    if keys & DEGRADED_STATUSES:
        return "degraded"
    if keys & GOOD_STATUSES:
        return "healthy"
    return "unknown"


def level_status(rollup: Mapping[str, object], level: str) -> str:
    levels = rollup.get("levels")
    counts = levels.get(level, {}) if isinstance(levels, dict) else {}
    return status_from_counts(counts)


def _read_rollup_file(path: Path) -> list[dict[str, object]]:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    rows: list[dict[str, object]] = []
    for line in lines:
        try:
            value = json.loads(line)
        except (TypeError, ValueError):
            continue
        valid = _valid_aggregate(value)
        finalized = _finalize(valid) if valid is not None else None
        if finalized is not None:
            rows.append(finalized)
    return rows


def read_health_rollups(
    runtime_root: Path,
    *,
    now: datetime | None = None,
    window: timedelta = timedelta(days=1),
) -> list[dict[str, object]]:
    """Read bounded aggregates for one time window, including the current bucket."""

    current = (now or datetime.now(UTC)).astimezone(UTC)
    start = current - window
    directory = runtime_root / METRICS_DIRECTORY / HEALTH_ROLLUP_DIRECTORY
    rows: list[dict[str, object]] = []
    if directory.is_dir():
        date = start.date()
        end_date = current.date()
        while date <= end_date:
            rows.extend(_read_rollup_file(directory / f"{date:%Y-%m-%d}.jsonl"))
            date += timedelta(days=1)
    state = _valid_aggregate(_read_json(_state_path(runtime_root)))
    current_row = _finalize(state) if state is not None else None
    if current_row is not None:
        rows.append(current_row)
    unique: dict[str, dict[str, object]] = {}
    for row in rows:
        timestamp = parse_timestamp(row.get("bucket_start"))
        if timestamp is not None and start <= timestamp <= current:
            unique[timestamp.isoformat()] = row
    return [unique[key] for key in sorted(unique)]


def window_summary(rows: list[Mapping[str, object]], *, window: timedelta) -> dict[str, object]:
    expected = max(1, math.ceil(window.total_seconds() / BUCKET_SECONDS))
    usable = [row for row in rows if int(row.get("sample_count", 0)) > 0]
    return {
        "available_buckets": len(usable),
        "expected_buckets": expected,
        "coverage_percent": round(min(100.0, len(usable) * 100 / expected), 1),
        "overall": {
            "healthy": sum(1 for row in usable if status_from_counts(row.get("overall")) == "healthy"),
            "degraded": sum(1 for row in usable if status_from_counts(row.get("overall")) == "degraded"),
            "critical": sum(1 for row in usable if status_from_counts(row.get("overall")) == "critical"),
            "unknown": sum(1 for row in usable if status_from_counts(row.get("overall")) == "unknown"),
        },
    }
