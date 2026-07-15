"""Render all Web Operations Console surfaces against five safe synthetic states.

Run this with the Streamlit-enabled Analytics virtual environment. This is a
deterministic rendering contract check; live LAN and browser visual validation
remain separate operations.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_VIEWS = ["DashBoard", "推移", "セッション", "操作履歴", "障害", "改善レポート", "タスク", "ログ"]


def _snapshot(now: datetime, status: str) -> dict[str, object]:
    failed = status == "critical"
    degraded = status == "degraded"
    return {
        "checked_at": now.isoformat(),
        "overall": status,
        "checks": [
            {"name": "TCP 8501", "level": "L1", "status": "failed" if failed else "ok", "detail": "synthetic", "latency_ms": 33},
            {"name": "Streamlit health", "level": "L1", "status": "ok" if not failed else "failed", "detail": "synthetic", "latency_ms": 48},
            {"name": "Streamlit page", "level": "L2", "status": "failed" if degraded else "ok", "detail": "synthetic", "latency_ms": 72},
            {"name": "user data", "level": "L3", "status": "ok", "detail": "synthetic", "latency_ms": 3},
        ],
        "storage": [
            {"name": "SMAI data", "status": "ok", "free_percent": 61.2, "free_bytes": 61 * 1024**3},
            {"name": "Runtime", "status": "ok", "free_percent": 58.7, "free_bytes": 42 * 1024**3},
        ],
    }


def _seed(project_root: Path, runtime_root: Path, status: str, *, event_count: int) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    state = project_root / "data" / "ops" / "server_ops"
    state.mkdir(parents=True, exist_ok=True)
    (state / "health_snapshot.json").write_text(json.dumps(_snapshot(now, status), ensure_ascii=False), encoding="utf-8")
    (state / "activity_state.json").write_text(
        json.dumps(
            {
                "sessions": {
                    "desktop-visual": {"last_seen_at": now.isoformat(), "user_id": "local-user", "profile_name": "Local User", "device_id": "device-pc", "client_type": "desktop", "connection_state": "connected"},
                    "phone-visual": {"last_seen_at": (now - timedelta(seconds=30)).isoformat(), "user_id": "mobile-user", "profile_name": "Mobile User", "device_id": "device-phone", "client_type": "smartphone", "connection_state": "connected"},
                    "tablet-visual": {"last_seen_at": (now - timedelta(minutes=4)).isoformat(), "user_id": "tablet-user", "profile_name": "Tablet User", "device_id": "device-tablet", "client_type": "tablet", "connection_state": "connected"},
                },
                "operations": {"market_refresh": {"status": "running"}, "backup_check": {"status": "queued"}},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    runtime_root.mkdir(parents=True, exist_ok=True)
    (runtime_root / "backup_restore_smoke.json").write_text(
        json.dumps({"checked_at": now.isoformat(), "overall": "healthy", "detail": "isolated restore verified"}, ensure_ascii=False),
        encoding="utf-8",
    )
    audit = runtime_root / "audit"
    audit.mkdir(parents=True, exist_ok=True)
    events = []
    for index in range(event_count):
        result = "critical" if status == "critical" and index == 0 else "failed" if status == "degraded" and index == 0 else "ok"
        events.append(
            {
                "timestamp": (now - timedelta(minutes=index)).isoformat(),
                "user_id": "local-user",
                "action": "synthetic_operation",
                "target": f"target-{index}",
                "result": result,
                "device_id": "device-pc",
                "duration_ms": 42 + index,
            }
        )
    (audit / "events.jsonl").write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in events), encoding="utf-8")


def _run_render(case: str, status: str, *, event_count: int) -> None:
    with tempfile.TemporaryDirectory(prefix="smai-web-render-", dir=str(REPOSITORY_ROOT)) as directory:
        root = Path(directory)
        project_root, runtime_root = root / "project", root / "runtime"
        _seed(project_root, runtime_root, status, event_count=event_count)
        environment = dict(os.environ)
        environment["SMAI_PROJECT_ROOT"] = str(project_root)
        environment["SMAI_RUNTIME_ROOT"] = str(runtime_root)
        environment["SMAI_ANALYTICS_TEST_SKIP_HEALTH_PROBE"] = "1"
        code = "\n".join(
            [
                "from streamlit.testing.v1 import AppTest",
                "app = AppTest.from_file('analytics_web.py')",
                "app.run(timeout=30)",
                f"expected = {EXPECTED_VIEWS!r}",
                "assert not app.exception, app.exception",
                "assert len(app.radio) == 1, app.radio",
                "assert app.radio[0].options == expected, app.radio[0].options",
                "for view in expected:",
                "    app.radio[0].set_value(view)",
                "    app.run(timeout=30)",
                "    assert not app.exception, (view, app.exception)",
                "    assert app.radio[0].value == view, (view, app.radio[0].value)",
                "    assert len(app.markdown) >= 3, (view, len(app.markdown))",
                f"print('WEB_RENDER_{case}=OK')",
            ]
        )
        result = subprocess.run([sys.executable, "-c", code], cwd=REPOSITORY_ROOT, env=environment, text=True, capture_output=True, check=False)
        if result.returncode != 0:
            raise RuntimeError(f"{case} failed:\n{result.stdout}\n{result.stderr}")
        print(result.stdout.strip())


def main() -> None:
    cases = (
        ("PASS_1_HEALTHY", "healthy", 3),
        ("PASS_2_DEGRADED", "degraded", 4),
        ("PASS_3_CRITICAL", "critical", 5),
        ("PASS_4_HIGH_VOLUME", "healthy", 100),
        ("PASS_5_RECOVERY", "healthy", 1),
    )
    for case, status, event_count in cases:
        _run_render(case, status, event_count=event_count)


if __name__ == "__main__":
    main()
