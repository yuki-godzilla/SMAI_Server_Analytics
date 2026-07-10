from __future__ import annotations

import json
import os
import socket
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

PROJECT_ROOT = Path(os.environ.get("SMAI_PROJECT_ROOT", r"C:\Users\user\workspace\SMAI_Projects\Smart_Market_AI"))
RUNTIME_ROOT = Path(os.environ.get("SMAI_RUNTIME_ROOT", r"C:\Users\user\workspace\SMAI_Projects\SMAI_Server_Runtime"))
SNAPSHOT_PATH = PROJECT_ROOT / "data/ops/server_ops/health_snapshot.json"
LOG_PATH = RUNTIME_ROOT / "logs/health.jsonl"


@dataclass(frozen=True)
class Check:
    name: str
    level: str
    status: str
    detail: str


def _url_ok(url: str, expected: bytes | None = None) -> tuple[bool, str]:
    try:
        with urlopen(url, timeout=2.0) as response:
            body = response.read(4096)
            ok = 200 <= response.status < 400 and (expected is None or body.strip().lower() == expected)
            return ok, f"HTTP {response.status}" if ok else "unexpected response"
    except (OSError, URLError) as exc:
        return False, type(exc).__name__


def collect() -> dict[str, object]:
    checks: list[Check] = []
    try:
        with socket.create_connection(("127.0.0.1", 8501), timeout=1):
            checks.append(Check("TCP 8501", "L1", "ok", "listener accepting connections"))
    except OSError as exc:
        checks.append(Check("TCP 8501", "L1", "failed", type(exc).__name__))
    for name, url, expected, level in (
        ("Streamlit health", "http://127.0.0.1:8501/_stcore/health", b"ok", "L1"),
        ("Streamlit page", "http://127.0.0.1:8501/", None, "L2"),
    ):
        ok, detail = _url_ok(url, expected)
        checks.append(Check(name, level, "ok" if ok else "failed", detail))
    for name, path in (("server ops state", PROJECT_ROOT / "data/ops/server_ops"), ("user data", PROJECT_ROOT / "data/user")):
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".health_probe.tmp"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            checks.append(Check(name, "L3", "ok", "read/write available"))
        except OSError as exc:
            checks.append(Check(name, "L3", "failed", type(exc).__name__))
    overall = "critical" if any(c.level == "L1" and c.status == "failed" for c in checks) else "degraded" if any(c.status == "failed" for c in checks) else "healthy"
    return {"checked_at": datetime.now(UTC).isoformat(), "overall": overall, "checks": [asdict(c) for c in checks]}


def main() -> int:
    payload = collect()
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    RUNTIME_ROOT.joinpath("logs").mkdir(parents=True, exist_ok=True)
    temporary = SNAPSHOT_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(SNAPSHOT_PATH)
    with LOG_PATH.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False) + "\n")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["overall"] != "critical" else 1


if __name__ == "__main__":
    raise SystemExit(main())

