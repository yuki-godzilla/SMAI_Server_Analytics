"""Fail-closed freshness checks for SMAI's local data update contracts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class FreshnessPolicy:
    name: str
    relative_path: str
    stale_after: timedelta
    critical_after: timedelta


POLICIES = (
    FreshnessPolicy(
        name="Market news freshness",
        relative_path="data/cache/news_update_status.json",
        stale_after=timedelta(hours=24),
        critical_after=timedelta(hours=48),
    ),
    FreshnessPolicy(
        name="Symbol data freshness",
        relative_path="data/cache/symbol_refresh_status.json",
        stale_after=timedelta(hours=26),
        critical_after=timedelta(hours=48),
    ),
)


def parse_timestamp(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _read_status(path: Path) -> Mapping[str, object] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _failure_count(status: Mapping[str, object]) -> int | None:
    value = status.get("consecutive_failures")
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    return None


def classify(policy: FreshnessPolicy, status: Mapping[str, object] | None, *, now: datetime) -> dict[str, object]:
    """Classify a status file without treating missing or malformed data as fresh."""

    if status is None:
        return {"name": policy.name, "level": "L2", "status": "unknown", "detail": "更新状態を読み取れません"}
    succeeded_at = parse_timestamp(status.get("last_success_at"))
    failures = _failure_count(status)
    if succeeded_at is None or failures is None:
        return {"name": policy.name, "level": "L2", "status": "unknown", "detail": "最終成功時刻または失敗回数を確認できません"}
    age = max(timedelta(), now.astimezone(UTC) - succeeded_at)
    minutes = int(age.total_seconds() // 60)
    if failures >= 4 or age > policy.critical_after:
        reason = f"連続失敗 {failures} 回" if failures >= 4 else f"最終成功から {minutes} 分経過"
        return {"name": policy.name, "level": "L2", "status": "critical", "detail": f"{reason}（更新停止の可能性）"}
    if failures >= 2 or age > policy.stale_after:
        reason = f"連続失敗 {failures} 回" if failures >= 2 else f"最終成功から {minutes} 分経過"
        return {"name": policy.name, "level": "L2", "status": "degraded", "detail": f"{reason}（鮮度を確認）"}
    if failures:
        return {"name": policy.name, "level": "L2", "status": "degraded", "detail": f"直近に失敗 {failures} 回（最終成功から {minutes} 分）"}
    return {"name": policy.name, "level": "L2", "status": "ok", "detail": f"最終成功から {minutes} 分"}


def collect_checks(project_root: Path, *, now: datetime | None = None) -> list[dict[str, object]]:
    current = (now or datetime.now(UTC)).astimezone(UTC)
    return [classify(policy, _read_status(project_root / policy.relative_path), now=current) for policy in POLICIES]
