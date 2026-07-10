from __future__ import annotations

import hashlib
import json
import os
import platform
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Mapping

RUNTIME_ROOT = Path(os.environ.get("SMAI_RUNTIME_ROOT", r"C:\Users\user\workspace\SMAI_Server_Runtime"))
EVENT_LOG = RUNTIME_ROOT / "audit/events.jsonl"
DEVICE_SALT_PATH = RUNTIME_ROOT / "audit/device_salt"


def _device_id() -> str:
    DEVICE_SALT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DEVICE_SALT_PATH.exists():
        salt = DEVICE_SALT_PATH.read_bytes()
    else:
        salt = uuid.uuid4().bytes
        DEVICE_SALT_PATH.write_bytes(salt)
    raw = f"{platform.node()}|{platform.system()}|{platform.release()}".encode()
    return hashlib.sha256(salt + raw).hexdigest()[:16]


def record_event(*, user_id: str, action: str, target: str = "", result: str = "ok", duration_ms: int | None = None, metadata: Mapping[str, object] | None = None) -> None:
    payload: dict[str, object] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "user_id": user_id[:100],
        "action": action[:100],
        "target": target[:200],
        "result": result[:40],
        "device_id": _device_id(),
        "platform": platform.system(),
    }
    if duration_ms is not None:
        payload["duration_ms"] = max(0, int(duration_ms))
    if metadata:
        payload["metadata"] = {str(key)[:50]: str(value)[:200] for key, value in metadata.items() if key not in {"token", "secret", "password", "topic", "input"}}
    EVENT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with EVENT_LOG.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False) + "\n")

