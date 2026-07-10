from __future__ import annotations

import json
import os
import subprocess
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import ttk

PROJECT_ROOT = Path(os.environ.get("SMAI_PROJECT_ROOT", r"C:\Users\user\workspace\Smart_Market_AI"))
RUNTIME_ROOT = Path(os.environ.get("SMAI_RUNTIME_ROOT", r"C:\Users\user\workspace\SMAI_Server_Runtime"))
SNAPSHOT = PROJECT_ROOT / "data/ops/server_ops/health_snapshot.json"
ACTIVITY = PROJECT_ROOT / "data/ops/server_ops/activity_state.json"
LOG_ROOTS = (RUNTIME_ROOT / "logs", PROJECT_ROOT / "logs/server_ops", PROJECT_ROOT / "logs/maintenance")


def _read_json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _recent_logs() -> list[str]:
    files = [path for root in LOG_ROOTS if root.exists() for path in root.glob("*.log")]
    files.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    lines: list[str] = []
    for path in files[:5]:
        try:
            tail = path.read_text(encoding="utf-8", errors="replace").splitlines()[-12:]
        except OSError:
            continue
        lines.extend([f"[{path.name}]", *tail])
    return lines[-80:]


class Dashboard:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("SMAI Server Operations")
        root.geometry("1120x720")
        root.minsize(820, 520)
        self.status = tk.StringVar(value="確認中")
        self.session = tk.StringVar(value="未取得")
        self.operations = tk.StringVar(value="未取得")
        self.checked = tk.StringVar(value="-")
        self._build()
        self.refresh()

    def _build(self) -> None:
        header = ttk.Frame(self.root, padding=12)
        header.pack(fill="x")
        ttk.Label(header, text="SMAI Server Operations", font=("Segoe UI", 18, "bold")).pack(side="left")
        ttk.Label(header, textvariable=self.status, font=("Segoe UI", 12, "bold")).pack(side="right")
        facts = ttk.Frame(self.root, padding=(12, 0, 12, 8))
        facts.pack(fill="x")
        for label, variable in (("ユーザー/セッション", self.session), ("処理中", self.operations), ("最終確認", self.checked)):
            box = ttk.LabelFrame(facts, text=label, padding=8)
            box.pack(side="left", fill="x", expand=True, padx=(0, 8))
            ttk.Label(box, textvariable=variable).pack(anchor="w")
        body = ttk.PanedWindow(self.root, orient="horizontal")
        body.pack(fill="both", expand=True, padx=12, pady=8)
        left = ttk.LabelFrame(body, text="ヘルスチェック", padding=8)
        right = ttk.LabelFrame(body, text="直近ログ", padding=8)
        body.add(left, weight=1)
        body.add(right, weight=2)
        self.health = tk.Text(left, width=42, state="disabled", wrap="word")
        self.health.pack(fill="both", expand=True)
        self.logs = tk.Text(right, state="disabled", wrap="none")
        self.logs.pack(fill="both", expand=True)
        ttk.Label(self.root, text=f"Project: {PROJECT_ROOT}    Runtime: {RUNTIME_ROOT}").pack(anchor="w", padx=12, pady=(0, 8))

    def _set_text(self, widget: tk.Text, lines: list[str]) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("end", "\n".join(lines))
        widget.configure(state="disabled")

    def refresh(self) -> None:
        try:
            subprocess.run([os.environ.get("PYTHON", "python"), str(Path(__file__).with_name("health.py"))], timeout=4, check=False, capture_output=True)
        except (OSError, subprocess.TimeoutExpired):
            pass
        snapshot = _read_json(SNAPSHOT)
        overall = str(snapshot.get("overall", "unknown"))
        self.status.set({"healthy": "● 正常", "degraded": "▲ 縮退", "critical": "■ 障害"}.get(overall, "? 未確認"))
        self.checked.set(str(snapshot.get("checked_at", "未取得")))
        checks = snapshot.get("checks", [])
        self._set_text(self.health, [f"overall: {overall}", *[f"{item.get('level')} {item.get('name')}: {item.get('status')} ({item.get('detail')})" for item in checks if isinstance(item, dict)]])
        activity = _read_json(ACTIVITY)
        sessions = activity.get("sessions", {})
        operations = activity.get("operations", {})
        self.session.set(f"{len(sessions) if isinstance(sessions, dict) else 0} 件")
        self.operations.set(f"{len(operations) if isinstance(operations, dict) else 0} 件")
        self._set_text(self.logs, _recent_logs())
        self.root.after(5000, self.refresh)


def main() -> None:
    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    root = tk.Tk()
    Dashboard(root)
    root.mainloop()


if __name__ == "__main__":
    main()
