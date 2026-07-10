from __future__ import annotations

import json
import os
import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import ttk

PROJECT_ROOT = Path(os.environ.get("SMAI_PROJECT_ROOT", r"C:\Users\user\workspace\SMAI_Projects\Smart_Market_AI"))
RUNTIME_ROOT = Path(os.environ.get("SMAI_RUNTIME_ROOT", r"C:\Users\user\workspace\SMAI_Projects\SMAI_Server_Runtime"))
SNAPSHOT = PROJECT_ROOT / "data/ops/server_ops/health_snapshot.json"
ACTIVITY = PROJECT_ROOT / "data/ops/server_ops/activity_state.json"
EVENT_LOG = RUNTIME_ROOT / "audit/events.jsonl"
LOG_ROOTS = (RUNTIME_ROOT / "logs", PROJECT_ROOT / "logs/server_ops", PROJECT_ROOT / "logs/maintenance")
TASKS = (
    "SmartMarketAI-Server-Autostart",
    "SmartMarketAI-Server-Watch",
    "SmartMarketAI-Symbol-Maintenance-IfDue",
)


def read_json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def read_events(limit: int = 200) -> list[dict[str, object]]:
    if not EVENT_LOG.exists():
        return []
    events: list[dict[str, object]] = []
    try:
        for line in EVENT_LOG.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]:
            try:
                value = json.loads(line)
                if isinstance(value, dict):
                    events.append(value)
            except ValueError:
                continue
    except OSError:
        return []
    return list(reversed(events))


def recent_logs() -> list[str]:
    files = [path for root in LOG_ROOTS if root.exists() for path in root.glob("*.log")]
    files.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    lines: list[str] = []
    for path in files[:5]:
        try:
            lines.extend([f"[{path.name}]", *path.read_text(encoding="utf-8", errors="replace").splitlines()[-12:]])
        except OSError:
            continue
    return lines[-100:]


def read_task_status() -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    for task in TASKS:
        try:
            result = subprocess.run(["schtasks.exe", "/Query", "/TN", f"\\{task}", "/FO", "LIST"], capture_output=True, text=True, timeout=2, check=False)
            values: dict[str, str] = {}
            for line in result.stdout.splitlines():
                if ":" in line:
                    key, value = line.split(":", 1)
                    values[key.strip()] = value.strip()
            rows.append((task, values.get("Status", "unknown"), values.get("Last Result", "unknown")))
        except (OSError, subprocess.TimeoutExpired):
            rows.append((task, "unknown", "task query unavailable"))
    return rows


class Dashboard:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("SMAI Analytics")
        root.geometry("1280x800")
        root.minsize(980, 600)
        self.status = tk.StringVar(value="Checking")
        self.session = tk.StringVar(value="-")
        self.operations = tk.StringVar(value="-")
        self.checked = tk.StringVar(value="-")
        self._build()
        self.refresh()

    def _build(self) -> None:
        header = ttk.Frame(self.root, padding=12)
        header.pack(fill="x")
        ttk.Label(header, text="SMAI Analytics", font=("Segoe UI", 20, "bold")).pack(side="left")
        ttk.Label(header, textvariable=self.status, font=("Segoe UI", 12, "bold")).pack(side="right")
        facts = ttk.Frame(self.root, padding=(12, 0, 12, 8))
        facts.pack(fill="x")
        for label, variable in (("Sessions", self.session), ("Active operations", self.operations), ("Last health check", self.checked)):
            box = ttk.LabelFrame(facts, text=label, padding=8)
            box.pack(side="left", fill="x", expand=True, padx=(0, 8))
            ttk.Label(box, textvariable=variable).pack(anchor="w")
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=12, pady=8)
        overview = ttk.Frame(notebook, padding=8)
        history = ttk.Frame(notebook, padding=8)
        incidents = ttk.Frame(notebook, padding=8)
        sessions = ttk.Frame(notebook, padding=8)
        tasks = ttk.Frame(notebook, padding=8)
        logs = ttk.Frame(notebook, padding=8)
        notebook.add(overview, text="Overview")
        notebook.add(sessions, text="Sessions")
        notebook.add(history, text="Activity History")
        notebook.add(incidents, text="Incidents")
        notebook.add(tasks, text="Tasks")
        notebook.add(logs, text="Logs")
        self.health = tk.Text(overview, state="disabled", wrap="word")
        self.health.pack(fill="both", expand=True)
        self.sessions = ttk.Treeview(sessions, columns=("user", "heartbeat", "state"), show="headings")
        for name, title in (("user", "Session / User"), ("heartbeat", "Last heartbeat"), ("state", "State")):
            self.sessions.heading(name, text=title)
            self.sessions.column(name, width=250 if name == "user" else 220, anchor="w")
        self.sessions.pack(fill="both", expand=True)
        controls = ttk.Frame(history)
        controls.pack(fill="x", pady=(0, 8))
        self.history_filter = tk.StringVar(value="all")
        ttk.Label(controls, text="Result").pack(side="left")
        ttk.Combobox(controls, textvariable=self.history_filter, values=("all", "ok", "failed", "cancelled"), state="readonly", width=14).pack(side="left", padx=8)
        ttk.Button(controls, text="Apply", command=self.refresh_history).pack(side="left")
        self.history = ttk.Treeview(history, columns=("time", "user", "action", "target", "result", "device", "duration"), show="headings")
        headings = {"time": "Time", "user": "User", "action": "Action", "target": "Target", "result": "Result", "device": "Device", "duration": "Duration"}
        for name, title in headings.items():
            self.history.heading(name, text=title)
            self.history.column(name, width=130 if name not in {"action", "target"} else 180, anchor="w")
        self.history.pack(fill="both", expand=True)
        self.incidents = tk.Text(incidents, state="disabled", wrap="word")
        self.incidents.pack(fill="both", expand=True)
        self.tasks = ttk.Treeview(tasks, columns=("task", "status", "result"), show="headings")
        for name, title in (("task", "Task"), ("status", "Status"), ("result", "Last result")):
            self.tasks.heading(name, text=title)
            self.tasks.column(name, width=340 if name == "task" else 180, anchor="w")
        self.tasks.pack(fill="both", expand=True)
        self.logs = tk.Text(logs, state="disabled", wrap="none")
        self.logs.pack(fill="both", expand=True)
        ttk.Label(self.root, text=f"Project: {PROJECT_ROOT}    Runtime: {RUNTIME_ROOT}").pack(anchor="w", padx=12, pady=(0, 8))

    @staticmethod
    def set_text(widget: tk.Text, lines: list[str]) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("end", "\n".join(lines))
        widget.configure(state="disabled")

    def refresh(self) -> None:
        try:
            subprocess.run([os.environ.get("PYTHON", "python"), str(Path(__file__).with_name("health.py"))], timeout=4, check=False, capture_output=True)
        except (OSError, subprocess.TimeoutExpired):
            pass
        snapshot = read_json(SNAPSHOT)
        overall = str(snapshot.get("overall", "unknown"))
        self.status.set({"healthy": "OK Healthy", "degraded": "WARN Degraded", "critical": "ERROR Critical"}.get(overall, "UNKNOWN"))
        self.checked.set(str(snapshot.get("checked_at", "not available")))
        checks = snapshot.get("checks", [])
        health_lines = [f"overall: {overall}"] + [f"{item.get('level')} {item.get('name')}: {item.get('status')} ({item.get('detail')})" for item in checks if isinstance(item, dict)]
        self.set_text(self.health, health_lines)
        activity = read_json(ACTIVITY)
        sessions = activity.get("sessions", {})
        operations = activity.get("operations", {})
        self.session.set(str(len(sessions) if isinstance(sessions, dict) else 0))
        self.operations.set(str(len(operations) if isinstance(operations, dict) else 0))
        for item in self.sessions.get_children():
            self.sessions.delete(item)
        if isinstance(sessions, dict):
            for session_id, heartbeat in sessions.items():
                self.sessions.insert("", "end", values=(session_id, heartbeat, "active"))
        self.refresh_history()
        incident_lines = [json.dumps(event, ensure_ascii=False) for event in read_events() if str(event.get("result", "")).lower() in {"failed", "error", "critical"}]
        self.set_text(self.incidents, incident_lines or ["No incidents recorded"])
        for item in self.tasks.get_children():
            self.tasks.delete(item)
        for task, status, result in read_task_status():
            self.tasks.insert("", "end", values=(task, status, result))
        self.set_text(self.logs, recent_logs())
        self.root.after(5000, self.refresh)

    def refresh_history(self) -> None:
        if not hasattr(self, "history"):
            return
        selected = self.history_filter.get()
        for item in self.history.get_children():
            self.history.delete(item)
        for event in read_events():
            if selected != "all" and str(event.get("result", "")).lower() != selected:
                continue
            self.history.insert("", "end", values=tuple(str(event.get(key, "")) for key in ("timestamp", "user_id", "action", "target", "result", "device_id", "duration_ms")))


def main() -> None:
    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    root = tk.Tk()
    Dashboard(root)
    root.mainloop()


if __name__ == "__main__":
    main()
