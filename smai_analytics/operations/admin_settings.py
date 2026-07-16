"""Local, administrator-owned preferences for the Analytics console.

The settings file intentionally lives in ``SMAI_Server_Runtime``.  It may
contain an administrator name and mailbox, so it must never become a tracked
repository artifact.  Credentials remain in Windows Credential Manager and
are not handled by this module.
"""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Mapping


RUNTIME_ROOT = Path(
    os.environ.get(
        "SMAI_RUNTIME_ROOT",
        r"C:\Users\user\workspace\SMAI_Projects\SMAI_Server_Runtime",
    )
)
SETTINGS_PATH = RUNTIME_ROOT / "incident_operations" / "administrator_settings.json"
SCHEMA_VERSION = 1
_EMAIL_PATTERN = re.compile(r"^[^@\s]{1,64}@[A-Za-z0-9.-]{1,189}$")


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()


def _load_json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


def _write_json_atomic(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _name(value: object) -> str:
    candidate = str(value or "").strip()
    if not candidate or len(candidate) > 80 or any(character in candidate for character in "\r\n"):
        raise ValueError("管理者名称は1〜80文字で入力してください。")
    return candidate


def _email(value: object) -> str:
    candidate = str(value or "").strip()
    if not _EMAIL_PATTERN.fullmatch(candidate) or "." not in candidate.rsplit("@", 1)[1]:
        raise ValueError("有効なメールアドレスを入力してください。")
    return candidate


def defaults() -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "administrator_name": "",
        "administrator_email": "",
        "notifications": {
            "incident_detection": True,
            "repair_report": True,
            "recovery_result": True,
        },
        # Enabling this grants a 24-hour lease for an isolated repair candidate
        # only.  Merge, deployment, restart, and push remain separately gated.
        "auto_repair_candidate": False,
    }


def load() -> dict[str, object]:
    """Read a normalized preferences document without treating corrupt data as enabled."""

    raw = _load_json(SETTINGS_PATH)
    result = defaults()
    result["administrator_name"] = str(raw.get("administrator_name") or "").strip()[:80]
    result["administrator_email"] = str(raw.get("administrator_email") or "").strip()[:254]
    raw_notifications = raw.get("notifications")
    if isinstance(raw_notifications, dict):
        notifications = result["notifications"]
        assert isinstance(notifications, dict)
        for key in notifications:
            # Missing values retain the safe, backwards-compatible default;
            # malformed non-booleans never enable a setting.
            if key in raw_notifications:
                notifications[key] = raw_notifications[key] is True
    result["auto_repair_candidate"] = raw.get("auto_repair_candidate") is True
    return result


def save_profile(*, administrator_name: str, administrator_email: str) -> dict[str, object]:
    settings = load()
    settings["administrator_name"] = _name(administrator_name)
    settings["administrator_email"] = _email(administrator_email)
    settings["updated_at"] = _timestamp()
    _write_json_atomic(SETTINGS_PATH, settings)
    return load()


def save_operations(*, incident_detection: bool, repair_report: bool, recovery_result: bool, auto_repair_candidate: bool) -> dict[str, object]:
    settings = load()
    settings["notifications"] = {
        "incident_detection": incident_detection is True,
        "repair_report": repair_report is True,
        "recovery_result": recovery_result is True,
    }
    settings["auto_repair_candidate"] = auto_repair_candidate is True
    settings["updated_at"] = _timestamp()
    _write_json_atomic(SETTINGS_PATH, settings)
    return load()


def notification_allowed(kind: object) -> bool:
    """Return the administrator's delivery preference for one report kind."""

    preferences = load()["notifications"]
    assert isinstance(preferences, dict)
    normalized = str(kind or "incident").casefold()
    if normalized in {"incident", "repeat"}:
        return preferences["incident_detection"] is True
    if normalized == "recovery":
        return preferences["recovery_result"] is True
    return preferences["repair_report"] is True


def auto_repair_candidate_requested() -> bool:
    return load()["auto_repair_candidate"] is True
