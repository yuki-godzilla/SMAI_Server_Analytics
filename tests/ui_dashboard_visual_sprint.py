"""Capture every Analytics tab at one viewport for a manual UI validation sprint.

This is intentionally separate from the unit suite.  It opens the real Tkinter
dashboard against isolated, synthetic operational data and captures the visible
window of every tab.  Run it only in an interactive Windows desktop session.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))


def _snapshot(at: datetime, *, status: str, latency: int, free_percent: float) -> dict[str, object]:
    check_status = "failed" if status == "critical" else "ok"
    return {
        "checked_at": at.isoformat(),
        "overall": status,
        "checks": [
            {"name": "TCP 8501", "level": "L1", "status": check_status, "latency_ms": latency},
            {"name": "Streamlit health", "level": "L1", "status": check_status, "latency_ms": latency + 5},
            {"name": "Streamlit page", "level": "L2", "status": "ok" if status != "degraded" else "failed", "latency_ms": latency + 15},
            {"name": "user data", "level": "L3", "status": "ok", "latency_ms": 3},
        ],
        "storage": [
            {"name": "SMAI data", "status": "ok", "free_percent": free_percent, "free_bytes": 80 * 1024**3},
            {"name": "Runtime", "status": "ok", "free_percent": free_percent - 1.5, "free_bytes": 40 * 1024**3},
        ],
    }


def _seed(project_root: Path, runtime_root: Path) -> None:
    import telemetry

    state_path = project_root / "data" / "ops" / "server_ops" / "activity_state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    state_path.write_text(
        json.dumps(
            {
                "sessions": {
                    "desktop-session-for-visual-check": {
                        "last_seen_at": now.isoformat(),
                        "user_id": "local-user",
                        "profile_name": "Local User",
                        "device_id": "device-desktop-visual",
                        "client_type": "desktop",
                        "connection_state": "connected",
                    },
                    "phone-session-for-visual-check": {
                        "last_seen_at": now.isoformat(),
                        "user_id": "mobile-user",
                        "profile_name": "Mobile User",
                        "device_id": "device-phone-visual",
                        "client_type": "smartphone",
                        "connection_state": "connected",
                    },
                },
                "operations": {"market_refresh": {"status": "running"}},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (state_path.parent / "health_snapshot.json").write_text(
        json.dumps(_snapshot(now, status="healthy", latency=42, free_percent=62.0), ensure_ascii=False),
        encoding="utf-8",
    )
    for index in range(8, -1, -1):
        moment = now - timedelta(minutes=index * 5)
        status = "critical" if index == 5 else "degraded" if index == 3 else "healthy"
        telemetry.record_health_snapshot(
            _snapshot(moment, status=status, latency=45 + index * 18, free_percent=62.0 - index * 0.6),
            runtime_root,
        )
    (runtime_root / "backup_restore_smoke.json").parent.mkdir(parents=True, exist_ok=True)
    (runtime_root / "backup_restore_smoke.json").write_text(
        json.dumps({"checked_at": now.isoformat(), "overall": "healthy", "detail": "isolated restore verified"}),
        encoding="utf-8",
    )


def capture_sprint(output: Path, *, width: int, height: int, sprint: str) -> list[Path]:
    # The environment must be fixed before importing modules that calculate
    # their project/runtime paths at import time.
    with tempfile.TemporaryDirectory(prefix="smai-ui-sprint-", dir=str(Path.cwd())) as directory:
        root_path = Path(directory)
        project_root = root_path / "project"
        runtime_root = root_path / "runtime"
        os.environ["SMAI_PROJECT_ROOT"] = str(project_root)
        os.environ["SMAI_RUNTIME_ROOT"] = str(runtime_root)
        _seed(project_root, runtime_root)
        import tkinter as tk
        from PIL import Image, ImageDraw, ImageGrab
        import dashboard

        app_root = tk.Tk()
        app = dashboard.Dashboard(app_root)
        viewport_width = min(width, max(720, app_root.winfo_screenwidth() - 28))
        viewport_height = min(height, max(520, app_root.winfo_screenheight() - 72))
        app_root.geometry(f"{viewport_width}x{viewport_height}+14+14")
        app_root.update_idletasks()
        app_root.update()
        time.sleep(0.15)
        app_root.update()
        output.mkdir(parents=True, exist_ok=True)
        captures: list[Path] = []
        extra_captures: list[Path] = []
        for index, tab_id in enumerate(app.notebook.tabs()):
            app.notebook.select(tab_id)
            app_root.update_idletasks()
            app_root.update()
            time.sleep(0.08)
            x, y = app_root.winfo_rootx(), app_root.winfo_rooty()
            image = ImageGrab.grab(bbox=(x, y, x + app_root.winfo_width(), y + app_root.winfo_height()))
            name = app.notebook.tab(tab_id, "text")
            path = output / f"{sprint}_{index + 1:02d}_{name}.png"
            image.save(path)
            captures.append(path)
            if tab_id == str(app.trends_page):
                app.trends_scroll_canvas.yview_moveto(1.0)
                app_root.update_idletasks()
                app_root.update()
                time.sleep(0.06)
                lower = ImageGrab.grab(bbox=(x, y, x + app_root.winfo_width(), y + app_root.winfo_height()))
                lower_path = output / f"{sprint}_{index + 1:02d}_{name}_lower.png"
                lower.save(lower_path)
                extra_captures.append(lower_path)
        app_root.destroy()

        thumb_width = 360
        thumb_height = max(1, round(viewport_height * thumb_width / viewport_width))
        sheet = Image.new("RGB", (thumb_width * 2, (thumb_height + 28) * 4), "#070D19")
        draw = ImageDraw.Draw(sheet)
        for index, path in enumerate(captures):
            image = Image.open(path).convert("RGB")
            image.thumbnail((thumb_width, thumb_height))
            x = (index % 2) * thumb_width
            y = (index // 2) * (thumb_height + 28)
            sheet.paste(image, (x, y + 24))
            draw.text((x + 8, y + 5), path.stem, fill="#E5EDF7")
        contact_sheet = output / f"{sprint}_contact_sheet.png"
        sheet.save(contact_sheet)
        return [*captures, *extra_captures, contact_sheet]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--height", type=int, required=True)
    parser.add_argument("--sprint", required=True)
    args = parser.parse_args()
    for path in capture_sprint(args.output, width=args.width, height=args.height, sprint=args.sprint):
        print(path)


if __name__ == "__main__":
    main()
