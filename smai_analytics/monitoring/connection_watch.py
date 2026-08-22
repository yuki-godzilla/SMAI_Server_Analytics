"""Persist privacy-safe connection observations for the Analytics dashboard."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable, Mapping

CLIENT_TYPES = ("desktop", "smartphone", "tablet")
ACTIVE_STATUSES = {"ok", "healthy", "active", "running"}
STATE_VERSION = 1
MAX_HISTORY_EVENTS = 500


def _empty_state() -> dict[str, object]:
    return {
        "version": STATE_VERSION,
        "updated_at": "",
        "sessions": {},
        "devices": {},
        "events": [],
    }


def _valid_state(value: object) -> bool:
    if not isinstance(value, dict) or value.get("version") != STATE_VERSION:
        return False
    sessions, devices, events = value.get("sessions"), value.get("devices"), value.get("events")

    def valid_session(item: object) -> bool:
        return isinstance(item, dict) and all(
            isinstance(item.get(key), str) for key in ("client_type", "device_id", "status")
        )

    def valid_device(item: object) -> bool:
        return isinstance(item, dict) and all(
            isinstance(item.get(key), str) for key in ("client_type", "first_seen_at", "last_seen_at")
        )

    def valid_event(item: object) -> bool:
        return isinstance(item, dict) and all(
            isinstance(item.get(key), str)
            for key in ("observed_at", "session_id", "client_type", "event", "status")
        )

    return (
        isinstance(value.get("updated_at"), str)
        and isinstance(sessions, dict)
        and isinstance(devices, dict)
        and isinstance(events, list)
        and all(isinstance(key, str) and valid_session(item) for key, item in sessions.items())
        and all(isinstance(key, str) and valid_device(item) for key, item in devices.items())
        and all(valid_event(item) for item in events)
    )


def read(path: Path) -> dict[str, object]:
    """Read the durable tracker state without treating corruption as empty data."""

    if not path.exists():
        return {"ok": True, "available": False, "state": _empty_state(), "reason": "not started"}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {"ok": False, "available": False, "state": _empty_state(), "reason": "state unreadable"}
    if not _valid_state(value):
        return {"ok": False, "available": False, "state": _empty_state(), "reason": "state invalid"}
    return {"ok": True, "available": True, "state": value, "reason": ""}


def _atomic_write(path: Path, state: Mapping[str, object]) -> bool:
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)
        return True
    except OSError:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        return False


def _normalized_sessions(sessions: Iterable[Mapping[str, object]]) -> dict[str, dict[str, str]]:
    normalized: dict[str, dict[str, str]] = {}
    for raw in sessions:
        session_id = str(raw.get("session_id") or "").strip()[:160]
        if not session_id:
            continue
        normalized[session_id] = {
            "client_type": str(raw.get("client_type") or "unknown").strip().casefold()[:40],
            "device_id": str(raw.get("device_id") or "").strip()[:160],
            "status": str(raw.get("status") or "unknown").strip().casefold()[:40],
        }
    return normalized


def _event(*, observed_at: str, session_id: str, client_type: str, event: str, status: str) -> dict[str, str]:
    return {
        "observed_at": observed_at,
        "session_id": session_id[:160],
        "client_type": client_type[:40],
        "event": event,
        "status": status[:40],
    }


def observe(
    sessions: Iterable[Mapping[str, object]],
    path: Path,
    *,
    observed_at: datetime | None = None,
) -> dict[str, object]:
    """Save state transitions from a readable current-session snapshot.

    A missing session is recorded as an observation loss, not as a confirmed
    disconnect.  The tracker cannot infer a network state after the source
    record has disappeared.
    """

    loaded = read(path)
    if not bool(loaded["ok"]):
        return loaded
    state = loaded["state"]
    if not isinstance(state, dict):  # Defensive guard for untyped JSON input.
        return {"ok": False, "available": False, "state": _empty_state(), "reason": "state invalid"}
    now = (observed_at or datetime.now(UTC)).astimezone(UTC).isoformat()
    previous_sessions = state["sessions"]
    devices = state["devices"]
    events = state["events"]
    if not isinstance(previous_sessions, dict) or not isinstance(devices, dict) or not isinstance(events, list):
        return {"ok": False, "available": False, "state": _empty_state(), "reason": "state invalid"}

    current_sessions = _normalized_sessions(sessions)
    next_sessions: dict[str, dict[str, str]] = {}
    next_events = [item for item in events if isinstance(item, dict)]
    for session_id, current in current_sessions.items():
        previous = previous_sessions.get(session_id)
        previous_status = str(previous.get("status") or "unknown") if isinstance(previous, dict) else ""
        previous_type = str(previous.get("client_type") or "unknown") if isinstance(previous, dict) else ""
        if not isinstance(previous, dict):
            next_events.append(
                _event(
                    observed_at=now,
                    session_id=session_id,
                    client_type=current["client_type"],
                    event="observed",
                    status=current["status"],
                )
            )
        elif previous_status != current["status"] or previous_type != current["client_type"]:
            next_events.append(
                _event(
                    observed_at=now,
                    session_id=session_id,
                    client_type=current["client_type"],
                    event="state_changed",
                    status=current["status"],
                )
            )
        next_sessions[session_id] = current
        device_id = current["device_id"]
        if device_id and current["client_type"] in CLIENT_TYPES:
            known = devices.get(device_id)
            first_seen_at = str(known.get("first_seen_at") or now) if isinstance(known, dict) else now
            devices[device_id] = {
                "client_type": current["client_type"],
                "first_seen_at": first_seen_at,
                "last_seen_at": now,
            }

    for session_id, previous in previous_sessions.items():
        if session_id in current_sessions or not isinstance(previous, dict):
            continue
        next_events.append(
            _event(
                observed_at=now,
                session_id=str(session_id),
                client_type=str(previous.get("client_type") or "unknown"),
                event="observation_lost",
                status="unknown",
            )
        )

    state["updated_at"] = now
    state["sessions"] = next_sessions
    state["devices"] = devices
    state["events"] = next_events[-MAX_HISTORY_EVENTS:]
    if not _atomic_write(path, state):
        return {"ok": False, "available": bool(loaded["available"]), "state": state, "reason": "state write failed"}
    return {"ok": True, "available": True, "state": state, "reason": ""}


def summary(state: Mapping[str, object]) -> dict[str, object]:
    """Return exact current and cumulative counts from a valid tracker state."""

    current = {client_type: 0 for client_type in CLIENT_TYPES}
    cumulative = {client_type: 0 for client_type in CLIENT_TYPES}
    unlinked_current = {client_type: 0 for client_type in CLIENT_TYPES}
    sessions = state.get("sessions")
    devices = state.get("devices")
    if not isinstance(sessions, dict) or not isinstance(devices, dict):
        return {"current": current, "cumulative": cumulative, "total_cumulative": 0, "unlinked_current": unlinked_current}
    for session in sessions.values():
        if not isinstance(session, dict):
            continue
        client_type = str(session.get("client_type") or "unknown")
        if client_type not in CLIENT_TYPES or str(session.get("status") or "unknown") not in ACTIVE_STATUSES:
            continue
        current[client_type] += 1
        if not str(session.get("device_id") or ""):
            unlinked_current[client_type] += 1
    for device in devices.values():
        if not isinstance(device, dict):
            continue
        client_type = str(device.get("client_type") or "unknown")
        if client_type in CLIENT_TYPES:
            cumulative[client_type] += 1
    return {
        "current": current,
        "cumulative": cumulative,
        "total_cumulative": sum(cumulative.values()),
        "unlinked_current": unlinked_current,
    }
