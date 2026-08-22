"""Fail-closed preflight for scheduled Windows host maintenance."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Mapping

PROJECT_ROOT = Path(os.environ.get("SMAI_PROJECT_ROOT", r"C:\Users\user\workspace\SMAI_Projects\Smart_Market_AI"))
RUNTIME_ROOT = Path(os.environ.get("SMAI_RUNTIME_ROOT", r"C:\Users\user\workspace\SMAI_Projects\SMAI_Server_Runtime"))
ACTIVITY_PATH = PROJECT_ROOT / "data" / "ops" / "server_ops" / "activity_state.json"
HEALTH_PATH = PROJECT_ROOT / "data" / "ops" / "server_ops" / "health_snapshot.json"
STATE_PATH = RUNTIME_ROOT / "host_maintenance" / "state.json"


@dataclass(frozen=True)
class Preflight:
    checked_at: str
    status: str
    safe_to_restart: bool
    blockers: tuple[str, ...]
    active_sessions: int
    busy_operations: int


def parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=parsed.tzinfo or UTC).astimezone(UTC)


def read_json(path: Path) -> dict[str, object] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def evaluate_preflight(
    activity: Mapping[str, object] | None,
    health: Mapping[str, object] | None,
    *,
    now: datetime | None = None,
    session_quiet_minutes: int = 15,
) -> Preflight:
    """Permit a host restart only with fresh healthy evidence and no active work."""

    current = (now or datetime.now(UTC)).astimezone(UTC)
    blockers: list[str] = []
    active_sessions = 0
    busy_operations = 0
    quiet_after = current - timedelta(minutes=session_quiet_minutes)

    if activity is None:
        blockers.append("activity_state_unavailable")
    else:
        sessions = activity.get("sessions")
        if not isinstance(sessions, dict):
            blockers.append("activity_sessions_invalid")
        else:
            for value in sessions.values():
                seen = parse_timestamp(value.get("last_seen_at") if isinstance(value, dict) else None)
                if seen is None:
                    blockers.append("activity_session_timestamp_invalid")
                elif seen >= quiet_after:
                    active_sessions += 1
        operations = activity.get("operations")
        if not isinstance(operations, dict):
            blockers.append("activity_operations_invalid")
        else:
            busy_operations = len(operations)

    if active_sessions:
        blockers.append("active_sessions")
    if busy_operations:
        blockers.append("busy_operations")

    if health is None:
        blockers.append("health_snapshot_unavailable")
    else:
        checked_at = parse_timestamp(health.get("checked_at"))
        if checked_at is None:
            blockers.append("health_timestamp_invalid")
        elif current - checked_at > timedelta(minutes=10):
            blockers.append("health_snapshot_stale")
        if str(health.get("overall") or "").casefold() != "healthy":
            blockers.append("health_not_healthy")

    status = "ready" if not blockers else "deferred"
    return Preflight(
        checked_at=current.isoformat(),
        status=status,
        safe_to_restart=not blockers,
        blockers=tuple(sorted(set(blockers))),
        active_sessions=active_sessions,
        busy_operations=busy_operations,
    )


def write_preflight(result: Preflight, path: Path = STATE_PATH) -> bool:
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(json.dumps(asdict(result), ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(path)
        return True
    except OSError:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Check whether SMAI host maintenance may restart Windows.")
    parser.add_argument("action", choices=("preflight",))
    parser.add_argument("--session-quiet-minutes", type=int, default=15)
    args = parser.parse_args()
    if not 1 <= args.session_quiet_minutes <= 240:
        parser.error("--session-quiet-minutes must be between 1 and 240")
    result = evaluate_preflight(
        read_json(ACTIVITY_PATH),
        read_json(HEALTH_PATH),
        session_quiet_minutes=args.session_quiet_minutes,
    )
    if not write_preflight(result):
        print('{"status":"unknown","detail":"maintenance state could not be recorded"}')
        return 1
    print(json.dumps(asdict(result), ensure_ascii=False))
    return 0 if result.safe_to_restart else 20


if __name__ == "__main__":
    raise SystemExit(main())
