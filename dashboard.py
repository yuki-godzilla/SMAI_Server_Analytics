from __future__ import annotations

import json
import math
import os
import subprocess
import tkinter as tk
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tkinter import ttk

try:
    from PIL import Image, ImageTk
except ImportError:  # pragma: no cover - exercised on minimal Python installs
    Image = None
    ImageTk = None

PROJECT_ROOT = Path(os.environ.get("SMAI_PROJECT_ROOT", r"C:\Users\user\workspace\SMAI_Projects\Smart_Market_AI"))
RUNTIME_ROOT = Path(os.environ.get("SMAI_RUNTIME_ROOT", r"C:\Users\user\workspace\SMAI_Projects\SMAI_Server_Runtime"))
SNAPSHOT = PROJECT_ROOT / "data/ops/server_ops/health_snapshot.json"
ACTIVITY = PROJECT_ROOT / "data/ops/server_ops/activity_state.json"
EVENT_LOG = RUNTIME_ROOT / "audit/events.jsonl"
LOG_ROOTS = (RUNTIME_ROOT / "logs", PROJECT_ROOT / "logs/server_ops", PROJECT_ROOT / "logs/maintenance")
ASSET_ROOT = Path(__file__).with_name("assets")
ANALYTICS_LOGO = ASSET_ROOT / "smai-analytics-logo-transparent.png"
ANALYTICS_MASCOT = ASSET_ROOT / "smai-analytics-mascot.png"
ANALYTICS_WORDMARK = ASSET_ROOT / "smai-analytics-wordmark-v2-transparent.png"
TASKS = (
    "SMAI-Server-Analytics",
    "SmartMarketAI-Server-Autostart",
    "SmartMarketAI-Server-Watch",
    "SmartMarketAI-Symbol-Maintenance-IfDue",
)

COLORS = {
    "app": "#020510",
    "page": "#070D19",
    "surface": "#0A1220",
    "card": "#111F35",
    "card_hover": "#1B2E49",
    "elevated": "#213550",
    "text": "#E5EDF7",
    "heading": "#F8FBFF",
    "muted": "#AAB8C8",
    "border": "#354763",
    "border_strong": "#6680A2",
    "cyan": "#22D3EE",
    "blue": "#60A5FA",
    "green": "#34D399",
    "amber": "#FBBF24",
    "red": "#F87171",
}


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
        lines = EVENT_LOG.read_text(encoding="utf-8", errors="replace").splitlines()
        for line in lines[-limit:]:
            try:
                value = json.loads(line)
                if isinstance(value, dict):
                    events.append(value)
            except (TypeError, ValueError):
                continue
    except OSError:
        return []
    return list(reversed(events))


def session_details(session_id: object, value: object) -> dict[str, str]:
    """Read legacy timestamp sessions and the v2 descriptive session contract."""

    if isinstance(value, dict):
        return {
            "session_id": str(session_id),
            "last_seen_at": str(value.get("last_seen_at") or ""),
            "user_id": str(value.get("user_id") or ""),
            "profile_name": str(value.get("profile_name") or ""),
            "device_id": str(value.get("device_id") or ""),
            "platform": str(value.get("platform") or ""),
            "connection_state": str(value.get("connection_state") or "unknown"),
        }
    return {
        "session_id": str(session_id),
        "last_seen_at": str(value or ""),
        "user_id": "",
        "profile_name": "",
        "device_id": "",
        "platform": "",
        "connection_state": "unknown",
    }


def recent_logs() -> list[str]:
    files = [path for root in LOG_ROOTS if root.exists() for path in root.glob("*.log")]
    files.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    lines: list[str] = []
    for path in files[:5]:
        try:
            lines.extend([f"[{path.name}]", *path.read_text(encoding="utf-8", errors="replace").splitlines()[-12:]])
        except OSError:
            continue
    return lines[-100:] or ["No recent logs available"]


def read_task_status() -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    for task in TASKS:
        try:
            result = subprocess.run(
                ["schtasks.exe", "/Query", "/TN", f"\\{task}", "/FO", "LIST"],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            values: dict[str, str] = {}
            for line in result.stdout.splitlines():
                if ":" in line:
                    key, value = line.split(":", 1)
                    values[key.strip()] = value.strip()
            status = values.get("Status", "unknown") if result.returncode == 0 else "unknown"
            result_text = values.get("Last Result", "unknown") if result.returncode == 0 else "task query unavailable"
            rows.append((task, status, result_text))
        except (OSError, subprocess.TimeoutExpired):
            rows.append((task, "unknown", "task query unavailable"))
    return rows


def format_timestamp(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return "not available"
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    except ValueError:
        return text


def compact_timestamp(value: object) -> str:
    parsed = parse_timestamp(value)
    if parsed is None:
        return "時刻不明"
    return parsed.astimezone().strftime("%H:%M:%S")


def parse_timestamp(value: object) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed
    except ValueError:
        return None


def relative_time(value: object) -> str:
    parsed = parse_timestamp(value)
    if parsed is None:
        return "時刻不明"
    seconds = max(0, int((datetime.now(UTC) - parsed.astimezone(UTC)).total_seconds()))
    if seconds < 60:
        return f"{seconds}秒前"
    if seconds < 3600:
        return f"{seconds // 60}分前"
    if seconds < 86400:
        return f"{seconds // 3600}時間前"
    return f"{seconds // 86400}日前"


def event_within_window(value: object, window: str, *, now: datetime | None = None) -> bool:
    """Filter audit events by a fixed recent window without treating bad times as recent."""

    hours_by_window = {"24h": 24, "7d": 24 * 7, "30d": 24 * 30}
    if window == "all":
        return True
    parsed = parse_timestamp(value)
    hours = hours_by_window.get(window)
    if parsed is None or hours is None:
        return False
    current = now or datetime.now(UTC)
    return parsed.astimezone(UTC) >= current.astimezone(UTC) - timedelta(hours=hours)


def compact_id(value: object, limit: int = 18) -> str:
    text = str(value or "")
    return text if len(text) <= limit else f"{text[:8]}…{text[-6:]}"


def ui_scale_for_display(width: int, height: int) -> float:
    """Return a conservative content scale for large desktop displays.

    Tk's DPI scaling keeps fonts sharp, but it intentionally does not make a
    9pt operations console more legible just because there are twice as many
    pixels available.  This scale handles that layout decision separately.
    """

    desktop_scale = max(width / 1920, height / 1080)
    return max(1.0, min(1.65, desktop_scale))


class Dashboard:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("SMAI Analytics  |  Operations Console")
        self._configure_dpi_scaling()
        self._fit_window_to_screen()
        try:
            self.ui_scale = max(1.0, min(2.5, float(self.root.tk.call("tk", "scaling"))))
        except (tk.TclError, TypeError, ValueError):
            self.ui_scale = 1.0
        self.content_scale = ui_scale_for_display(self.root.winfo_screenwidth(), self.root.winfo_screenheight())
        self.root.configure(bg=COLORS["page"])
        self.status = tk.StringVar(value="CHECKING")
        self.status_detail = tk.StringVar(value="Collecting server health")
        self.session = tk.StringVar(value="-")
        self.operations = tk.StringVar(value="-")
        self.checked = tk.StringVar(value="-")
        self.refresh_state = tk.StringVar(value="Auto-refresh 5s")
        self.health_history: list[tuple[str, int]] = []
        self.session_rows: list[tuple[str, object, str]] = []
        self.activity_events: list[dict[str, object]] = []
        self.incident_events: list[dict[str, object]] = []
        self.incident_source_events: list[dict[str, object]] = []
        self.task_rows: list[tuple[str, str, str]] = []
        self.log_lines: list[str] = []
        self.logo_image = self._load_brand_image(ANALYTICS_LOGO, max_width=56, max_height=56)
        self.mascot_image = self._load_brand_image(ANALYTICS_MASCOT, max_width=150, max_height=150)
        # Keep the regenerated 3:1 wordmark's natural ratio; never stretch it to fill a wider slot.
        self.wordmark_image = self._load_brand_image(ANALYTICS_WORDMARK, max_width=500, max_height=130)
        self.check_statuses: dict[str, str] = {}
        self._configure_style()
        self._build()
        self.refresh()

    def _configure_dpi_scaling(self) -> None:
        """Align Tk logical units with the current Windows monitor DPI."""
        if os.name != "nt":
            return
        try:
            import ctypes

            dpi = int(ctypes.windll.user32.GetDpiForWindow(self.root.winfo_id()))
            if dpi > 0:
                self.root.tk.call("tk", "scaling", max(1.0, min(2.5, dpi / 72.0)))
        except (AttributeError, OSError, tk.TclError, TypeError, ValueError):
            return

    def _load_brand_image(self, path: Path, *, max_width: int, max_height: int) -> object | None:
        """Load a high-quality bounded header image with a Tk-only fallback."""
        if not path.is_file():
            return None
        max_width = max(1, round(max_width * self.ui_scale))
        max_height = max(1, round(max_height * self.ui_scale))
        try:
            if Image is not None and ImageTk is not None:
                with Image.open(path) as source:
                    source = source.convert("RGBA")
                    scale = min(max_width / source.width, max_height / source.height, 1.0)
                    size = (max(1, round(source.width * scale)), max(1, round(source.height * scale)))
                    resized = source.resize(size, Image.Resampling.LANCZOS)
                    return ImageTk.PhotoImage(resized)
            fallback_path = path.with_name(f"{path.stem}-header{path.suffix}")
            if self.ui_scale > 1.05:
                fallback_path = path
            image = tk.PhotoImage(file=str(fallback_path if fallback_path.is_file() else path))
            factor = max(1, math.ceil(image.width() / max_width), math.ceil(image.height() / max_height))
            return image.subsample(factor, factor) if factor > 1 else image
        except (AttributeError, OSError, ValueError, tk.TclError):
            return None

    def _fit_window_to_screen(self) -> None:
        """Fit the console inside the current display, including notebook PCs."""
        self.root.update_idletasks()
        screen_width = max(800, int(self.root.winfo_screenwidth()))
        screen_height = max(600, int(self.root.winfo_screenheight()))
        try:
            scaling = max(1.0, float(self.root.tk.call("tk", "scaling")))
        except (TypeError, ValueError, tk.TclError):
            scaling = 1.0
        base_width, base_height = screen_width, screen_height
        if os.name == "nt":
            try:
                import ctypes

                get_metrics = ctypes.windll.user32.GetSystemMetricsForDpi
                get_metrics.argtypes = [ctypes.c_int, ctypes.c_uint]
                get_metrics.restype = ctypes.c_int
                base_width = max(800, int(get_metrics(0, 96)))
                base_height = max(600, int(get_metrics(1, 96)))
            except (AttributeError, OSError):
                pass
        # Use the available desktop rather than a fixed 1360px ceiling.  The
        # console is designed for an always-on desktop and should make useful
        # use of 1440p/4K displays while still fitting smaller notebooks.
        min_width = max(720, int(980 / scaling))
        min_height = max(520, int(680 / scaling))
        # Geometry is already expressed in the monitor's desktop units.  Do
        # not divide by Tk scaling here: doing so makes a 200%-scaled 4K
        # desktop occupy only about half of the usable screen.
        width = max(min_width, int(base_width * 0.96))
        height = max(min_height, int(base_height * 0.92))
        width = min(width, screen_width - 20)
        height = min(height, screen_height - 56)
        self.root.minsize(min(min_width, width), min(min_height, height))
        x = max(0, (screen_width - width) // 2)
        y = max(0, (screen_height - height) // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def _font(self, size: float, weight: str = "normal", family: str = "Segoe UI") -> tuple[str, int, str]:
        """Use one legible typography scale across widgets and drawings."""
        return (family, max(8, round(size * self.content_scale)), weight)

    def _px(self, value: float, minimum: int = 1) -> int:
        return max(minimum, round(value * self.content_scale))

    def _configure_style(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("App.TFrame", background=COLORS["page"])
        style.configure("Surface.TFrame", background=COLORS["surface"])
        style.configure("Card.TFrame", background=COLORS["card"])
        style.configure("Title.TLabel", background=COLORS["page"], foreground=COLORS["heading"], font=self._font(24, "bold"))
        style.configure("Subtitle.TLabel", background=COLORS["page"], foreground=COLORS["muted"], font=self._font(11))
        style.configure("Section.TLabel", background=COLORS["surface"], foreground=COLORS["heading"], font=self._font(11, "bold"))
        style.configure("CardLabel.TLabel", background=COLORS["card"], foreground=COLORS["muted"], font=self._font(9, "bold"))
        style.configure("CardValue.TLabel", background=COLORS["card"], foreground=COLORS["heading"], font=self._font(20, "bold"))
        style.configure("CardMeta.TLabel", background=COLORS["card"], foreground=COLORS["muted"], font=self._font(10))
        style.configure("TNotebook", background=COLORS["page"], borderwidth=0, tabmargins=(0, 0, 0, 0))
        style.configure("TNotebook.Tab", background=COLORS["surface"], foreground=COLORS["muted"], padding=(self._px(18), self._px(9)), borderwidth=0, font=self._font(10, "bold"))
        style.map("TNotebook.Tab", background=[("selected", COLORS["card"])], foreground=[("selected", COLORS["cyan"])], expand=[("selected", (0, 1, 0, 0))])
        style.configure("Treeview", background=COLORS["surface"], fieldbackground=COLORS["surface"], foreground=COLORS["text"], rowheight=self._px(32), borderwidth=0, font=self._font(10))
        style.configure("Treeview.Heading", background=COLORS["elevated"], foreground=COLORS["heading"], relief="flat", font=self._font(10, "bold"))
        style.map("Treeview", background=[("selected", COLORS["card_hover"])], foreground=[("selected", COLORS["heading"])])
        style.configure("TButton", background=COLORS["elevated"], foreground=COLORS["heading"], borderwidth=1, padding=(self._px(12), self._px(7)), font=self._font(10, "bold"))
        style.map("TButton", background=[("active", COLORS["card_hover"])], foreground=[("active", COLORS["cyan"])])
        style.configure("TCombobox", fieldbackground=COLORS["surface"], background=COLORS["surface"], foreground=COLORS["text"])
        style.configure("TEntry", fieldbackground=COLORS["surface"], foreground=COLORS["text"], insertcolor=COLORS["text"])

    def _build(self) -> None:
        outer = ttk.Frame(self.root, style="App.TFrame", padding=(self._px(28), self._px(24), self._px(28), self._px(16)))
        outer.pack(fill="both", expand=True)
        header = ttk.Frame(outer, style="App.TFrame")
        header.pack(fill="x", pady=(0, self._px(16)))
        brand_block = ttk.Frame(header, style="App.TFrame")
        brand_block.pack(side="left")
        if self.wordmark_image is not None:
            tk.Label(brand_block, image=self.wordmark_image, bg=COLORS["page"], bd=0, highlightthickness=0).pack(anchor="w")
            ttk.Label(brand_block, text="Operations Console  /  Always-on local monitoring", style="Subtitle.TLabel").pack(anchor="w", pady=(self._px(4), 0))
        else:
            if self.logo_image is not None:
                tk.Label(brand_block, image=self.logo_image, bg=COLORS["page"], bd=0, highlightthickness=0).pack(side="left", padx=(0, 12))
            title_block = ttk.Frame(brand_block, style="App.TFrame")
            title_block.pack(side="left")
            ttk.Label(title_block, text="SMAI Analytics", style="Title.TLabel").pack(anchor="w")
            ttk.Label(title_block, text="Operations Console  /  Always-on local monitoring", style="Subtitle.TLabel").pack(anchor="w", pady=(3, 0))
        status_block = ttk.Frame(header, style="App.TFrame")
        status_block.pack(side="right", anchor="n")
        if self.mascot_image is not None:
            tk.Label(status_block, image=self.mascot_image, bg=COLORS["page"], bd=0, highlightthickness=0).pack(side="left", padx=(0, 12))
        status_text = ttk.Frame(status_block, style="App.TFrame")
        status_text.pack(side="left", anchor="n")
        self.status_label = tk.Label(status_text, textvariable=self.status, bg=COLORS["elevated"], fg=COLORS["cyan"], font=self._font(11, "bold"), padx=self._px(16), pady=self._px(8))
        self.status_label.pack(anchor="e")
        ttk.Label(status_text, textvariable=self.status_detail, style="Subtitle.TLabel").pack(anchor="e", pady=(5, 0))

        facts = ttk.Frame(outer, style="App.TFrame")
        facts.pack(fill="x", pady=(0, self._px(16)))
        facts.pack_propagate(False)
        facts.configure(height=self._px(124))
        facts.columnconfigure(0, weight=1, uniform="kpi")
        facts.columnconfigure(1, weight=1, uniform="kpi")
        facts.columnconfigure(2, weight=1, uniform="kpi")
        for index, (label, variable, meta) in enumerate((("ACTIVE SESSIONS", self.session, "Current activity state"), ("RUNNING OPERATIONS", self.operations, "In-progress work items"), ("LAST CHECK", self.checked, "Snapshot time / local"))):
            card = ttk.Frame(facts, style="Card.TFrame", padding=(self._px(18), self._px(15)))
            card.grid(row=0, column=index, sticky="nsew", padx=(0, self._px(12) if index < 2 else 0))
            ttk.Label(card, text=label, style="CardLabel.TLabel").pack(anchor="w")
            ttk.Label(card, textvariable=variable, style="CardValue.TLabel").pack(anchor="w", pady=(5, 2))
            ttk.Label(card, text=meta, style="CardMeta.TLabel").pack(anchor="w")

        notebook = ttk.Notebook(outer)
        notebook.pack(fill="both", expand=True)
        overview, sessions, history, incidents, tasks, logs = [ttk.Frame(notebook, style="Surface.TFrame", padding=self._px(16)) for _ in range(6)]
        for frame, name in ((overview, "Overview"), (sessions, "Sessions"), (history, "Activity History"), (incidents, "Incidents"), (tasks, "Tasks"), (logs, "Logs")):
            notebook.add(frame, text=name)
        overview.columnconfigure(0, weight=3)
        overview.columnconfigure(1, weight=2)
        overview.rowconfigure(0, weight=1)
        overview.rowconfigure(1, weight=1)
        map_panel = self._panel(overview, "SERVICE TOPOLOGY", "Live local service path")
        map_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=(0, 8))
        gauge_panel = self._panel(overview, "SYSTEM HEALTH", "Current health score")
        gauge_panel.grid(row=0, column=1, sticky="nsew", padx=(8, 0), pady=(0, 8))
        trend_panel = self._panel(overview, "HEALTH TIMELINE", "Recent refresh history")
        trend_panel.grid(row=1, column=0, sticky="nsew", padx=(0, 8), pady=(8, 0))
        checks_panel = self._panel(overview, "CHECK MATRIX", "L1 / L2 / L3 checks")
        checks_panel.grid(row=1, column=1, sticky="nsew", padx=(8, 0), pady=(8, 0))
        self.map_canvas = self._canvas(map_panel, height=220)
        self.map_canvas.pack(fill="both", expand=True, padx=self._px(14), pady=(0, self._px(14)))
        self.gauge_canvas = self._canvas(gauge_panel, height=220)
        self.gauge_canvas.pack(fill="both", expand=True, padx=self._px(14), pady=(0, self._px(14)))
        self.trend_canvas = self._canvas(trend_panel, height=190)
        self.trend_canvas.pack(fill="both", expand=True, padx=self._px(14), pady=(0, self._px(14)))
        self.health = self._canvas(checks_panel, height=190)
        self.health.pack(fill="both", expand=True, padx=self._px(14), pady=(0, self._px(14)))
        for canvas in (self.map_canvas, self.gauge_canvas, self.trend_canvas, self.health):
            canvas.bind("<Configure>", lambda _event: self._redraw_visuals())
        sessions_summary = self._panel(sessions, "SESSION PULSE", "接続中ユーザーとheartbeatの鮮度")
        sessions_summary.pack(fill="x", pady=(0, 10))
        self.session_canvas = self._canvas(sessions_summary, height=112)
        self.session_canvas.pack(fill="x", padx=12, pady=(0, 12))
        sessions_table = self._panel(sessions, "SESSION DETAILS", "詳細は診断用。識別子は短縮表示")
        sessions_table.pack(fill="both", expand=True)
        self.sessions = self._tree(sessions_table, (("user", "ユーザー / プロフィール", 240), ("heartbeat", "最終通信", 230), ("device", "端末擬似ID", 150), ("state", "状態", 150)))
        activity_summary = self._panel(history, "ACTIVITY PULSE", "操作量と結果の分布")
        activity_summary.pack(fill="x", pady=(0, 10))
        self.activity_canvas = self._canvas(activity_summary, height=112)
        self.activity_canvas.pack(fill="x", padx=12, pady=(0, 12))
        controls = ttk.Frame(history, style="Surface.TFrame")
        controls.pack(fill="x", pady=(0, 10))
        ttk.Label(controls, text="期間", style="Section.TLabel").pack(side="left")
        self.history_window_filter = tk.StringVar(value="24h")
        ttk.Combobox(controls, textvariable=self.history_window_filter, values=("24h", "7d", "30d", "all"), state="readonly", width=8).pack(side="left", padx=(8, 12))
        ttk.Label(controls, text="結果フィルター", style="Section.TLabel").pack(side="left")
        self.history_filter = tk.StringVar(value="all")
        ttk.Combobox(controls, textvariable=self.history_filter, values=("all", "ok", "failed", "cancelled"), state="readonly", width=14).pack(side="left", padx=10)
        ttk.Label(controls, text="ユーザー", style="Section.TLabel").pack(side="left", padx=(12, 4))
        self.history_user_filter = tk.StringVar()
        ttk.Entry(controls, textvariable=self.history_user_filter, width=16).pack(side="left")
        ttk.Label(controls, text="操作", style="Section.TLabel").pack(side="left", padx=(12, 4))
        self.history_action_filter = tk.StringVar()
        ttk.Entry(controls, textvariable=self.history_action_filter, width=18).pack(side="left")
        ttk.Button(controls, text="適用", command=self.refresh_history).pack(side="left", padx=(10, 4))
        ttk.Button(controls, text="クリア", command=self._clear_history_filters).pack(side="left")
        self.history = self._tree(history, (("time", "時刻", 180), ("user", "ユーザー", 140), ("action", "操作", 190), ("target", "対象", 220), ("result", "結果", 110), ("device", "端末", 130), ("duration", "所要時間", 100)))
        incident_summary = self._panel(incidents, "INCIDENT STATUS", "障害・失敗イベントと復旧確認")
        incident_summary.pack(fill="x", pady=(0, 10))
        self.incident_canvas = self._canvas(incident_summary, height=112)
        self.incident_canvas.pack(fill="x", padx=12, pady=(0, 12))
        incident_controls = ttk.Frame(incidents, style="Surface.TFrame")
        incident_controls.pack(fill="x", pady=(0, 10))
        ttk.Label(incident_controls, text="期間", style="Section.TLabel").pack(side="left")
        self.incident_window_filter = tk.StringVar(value="7d")
        ttk.Combobox(incident_controls, textvariable=self.incident_window_filter, values=("24h", "7d", "30d", "all"), state="readonly", width=8).pack(side="left", padx=(8, 12))
        ttk.Label(incident_controls, text="重要度フィルター", style="Section.TLabel").pack(side="left")
        self.incident_filter = tk.StringVar(value="all")
        ttk.Combobox(incident_controls, textvariable=self.incident_filter, values=("all", "failed", "error", "critical"), state="readonly", width=14).pack(side="left", padx=10)
        ttk.Button(incident_controls, text="適用", command=self.refresh_incidents).pack(side="left")
        incident_table = self._panel(incidents, "INCIDENT DETAILS", "failed / error / critical の直近イベント")
        incident_table.pack(fill="both", expand=True)
        self.incidents = self._tree(incident_table, (("time", "時刻", 190), ("action", "操作", 210), ("target", "対象", 280), ("result", "結果", 130)))
        task_summary = self._panel(tasks, "TASK COVERAGE", "Windows Scheduled Task の確認結果")
        task_summary.pack(fill="x", pady=(0, 10))
        self.task_canvas = self._canvas(task_summary, height=112)
        self.task_canvas.pack(fill="x", padx=12, pady=(0, 12))
        task_table = self._panel(tasks, "TASK DETAILS", "unknown は未登録または取得不能")
        task_table.pack(fill="both", expand=True)
        self.tasks = self._tree(task_table, (("task", "タスク", 390), ("status", "状態", 180), ("result", "最終結果", 230)))
        log_summary = self._panel(logs, "LOG SIGNAL", "直近100行の重要語を集計")
        log_summary.pack(fill="x", pady=(0, 10))
        self.log_canvas = self._canvas(log_summary, height=112)
        self.log_canvas.pack(fill="x", padx=12, pady=(0, 12))
        log_detail = self._panel(logs, "RECENT LOGS", "生ログは調査用。異常はIncidentsで確認")
        log_detail.pack(fill="both", expand=True)
        log_body = ttk.Frame(log_detail, style="Card.TFrame")
        log_body.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.logs = tk.Text(log_body, state="disabled", wrap="none", bg=COLORS["card"], fg=COLORS["text"], relief="flat", padx=self._px(14), pady=self._px(12), font=self._font(10, family="Consolas"), highlightthickness=0)
        log_y_scroll = ttk.Scrollbar(log_body, orient="vertical", command=self.logs.yview)
        log_x_scroll = ttk.Scrollbar(log_body, orient="horizontal", command=self.logs.xview)
        self.logs.configure(yscrollcommand=log_y_scroll.set, xscrollcommand=log_x_scroll.set)
        self.logs.grid(row=0, column=0, sticky="nsew")
        log_y_scroll.grid(row=0, column=1, sticky="ns")
        log_x_scroll.grid(row=1, column=0, sticky="ew")
        log_body.rowconfigure(0, weight=1)
        log_body.columnconfigure(0, weight=1)
        for canvas in (self.session_canvas, self.activity_canvas, self.incident_canvas, self.task_canvas, self.log_canvas):
            canvas.bind("<Configure>", lambda _event: self._draw_tab_visuals())
        footer = ttk.Frame(outer, style="App.TFrame")
        footer.pack(fill="x", pady=(10, 0))
        ttk.Label(footer, text=f"Project  {PROJECT_ROOT.name}    Runtime  {RUNTIME_ROOT.name}", style="Subtitle.TLabel").pack(side="left")
        ttk.Label(footer, textvariable=self.refresh_state, style="Subtitle.TLabel").pack(side="right")

    def _panel(self, parent: ttk.Frame, title: str, subtitle: str) -> ttk.Frame:
        panel = ttk.Frame(parent, style="Card.TFrame", padding=(self._px(14), self._px(12)))
        header = ttk.Frame(panel, style="Card.TFrame")
        header.pack(fill="x", pady=(0, self._px(10)))
        ttk.Label(header, text=title, style="CardLabel.TLabel").pack(side="left")
        ttk.Label(header, text=subtitle, style="CardMeta.TLabel").pack(side="right")
        return panel

    def _canvas(self, parent: ttk.Frame, *, height: int) -> tk.Canvas:
        return tk.Canvas(parent, height=self._px(height), bg=COLORS["card"], highlightthickness=0, bd=0)

    def _tree(self, parent: ttk.Frame, columns: tuple[tuple[str, str, int], ...]) -> ttk.Treeview:
        body = ttk.Frame(parent, style="Card.TFrame")
        body.pack(fill="both", expand=True)
        tree = ttk.Treeview(body, columns=tuple(item[0] for item in columns), show="headings")
        for name, title, width in columns:
            tree.heading(name, text=title)
            tree.column(name, width=self._px(width), minwidth=self._px(80), anchor="w")
        tree.tag_configure("healthy", foreground=COLORS["green"])
        tree.tag_configure("degraded", foreground=COLORS["amber"])
        tree.tag_configure("critical", foreground=COLORS["red"])
        tree.tag_configure("unknown", foreground=COLORS["muted"])
        y_scroll = ttk.Scrollbar(body, orient="vertical", command=tree.yview)
        x_scroll = ttk.Scrollbar(body, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)
        return tree

    @staticmethod
    def set_text(widget: tk.Text, lines: list[str]) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("end", "\n".join(lines))
        widget.configure(state="disabled")

    @staticmethod
    def _health_score(overall: str) -> int:
        return {"healthy": 100, "degraded": 62, "critical": 18}.get(overall, 0)

    @staticmethod
    def _status_color(status: str) -> str:
        return {"ok": COLORS["green"], "healthy": COLORS["green"], "active": COLORS["green"], "running": COLORS["green"], "ready": COLORS["green"], "degraded": COLORS["amber"], "stale": COLORS["amber"], "failed": COLORS["red"], "critical": COLORS["red"], "error": COLORS["red"], "unknown": COLORS["muted"]}.get(status.lower(), COLORS["muted"])

    @staticmethod
    def _tree_status_tag(status: object) -> str:
        normalized = str(status or "unknown").lower()
        if normalized in {"failed", "critical", "error"}:
            return "critical"
        if normalized in {"degraded", "stale", "cancelled", "disabled", "queued"}:
            return "degraded"
        if normalized in {"ok", "healthy", "active", "running", "ready"}:
            return "healthy"
        return "unknown"

    def _redraw_visuals(self) -> None:
        if not hasattr(self, "map_canvas"):
            return
        self._draw_service_map()
        self._draw_gauge()
        self._draw_trend()

    def _draw_service_map(self) -> None:
        canvas = self.map_canvas
        canvas.delete("all")
        width = max(canvas.winfo_width(), 400)
        height = max(canvas.winfo_height(), 180)
        nodes = [("SMAI UI", 0.17, 0.28), ("Streamlit", 0.50, 0.28), ("Runtime", 0.83, 0.28), ("Analytics", 0.50, 0.68)]
        points = {}
        for label, x, y in nodes:
            points[label] = (width * x, height * y)
        for left, right in (("SMAI UI", "Streamlit"), ("Streamlit", "Runtime"), ("Streamlit", "Analytics")):
            x1, y1 = points[left]
            x2, y2 = points[right]
            canvas.create_line(x1, y1, x2, y2, fill=COLORS["border_strong"], width=self._px(2))
            dot = self._px(3)
            canvas.create_oval((x1 + x2) / 2 - dot, (y1 + y2) / 2 - dot, (x1 + x2) / 2 + dot, (y1 + y2) / 2 + dot, fill=COLORS["cyan"], outline="")
        statuses = {
            "SMAI UI": self._service_status("smai ui"),
            "Streamlit": self._service_status("streamlit"),
            "Runtime": self._service_status("server ops", "runtime"),
            "Analytics": self.status.get().lower(),
        }
        for label, _, _ in nodes:
            x, y = points[label]
            color = self._status_color(statuses[label])
            radius = self._px(27)
            core = self._px(8)
            canvas.create_oval(x - radius, y - radius, x + radius, y + radius, fill=COLORS["elevated"], outline=color, width=self._px(2))
            canvas.create_oval(x - core, y - core, x + core, y + core, fill=color, outline="")
            canvas.create_text(x, min(y + self._px(40), height - self._px(10)), text=label, fill=COLORS["heading"], font=self._font(10, "bold"))
        canvas.create_text(self._px(16), self._px(16), text="LOCAL SERVICE FLOW", anchor="nw", fill=COLORS["muted"], font=self._font(9, "bold"))
        canvas.create_text(width - self._px(12), height - self._px(10), text="灰色 = health check 未計測", anchor="se", fill=COLORS["muted"], font=self._font(9))

    def _service_status(self, *keywords: str) -> str:
        """Resolve topology nodes only from readable health-check evidence."""
        matches = [
            status
            for name, status in self.check_statuses.items()
            if any(keyword in name for keyword in keywords)
        ]
        if not matches:
            return "unknown"
        priority = {"critical": 4, "error": 4, "failed": 4, "degraded": 3, "unknown": 2, "healthy": 1, "ok": 1}
        return max(matches, key=lambda item: priority.get(item, 2))

    def _draw_gauge(self) -> None:
        canvas = self.gauge_canvas
        canvas.delete("all")
        width = max(canvas.winfo_width(), 260)
        height = max(canvas.winfo_height(), 180)
        score = self._health_score(self.status.get().lower())
        color = self._status_color(self.status.get().lower())
        size = min(self._px(180), max(self._px(128), min(width - self._px(40), height - self._px(44))))
        cx, cy = width / 2, height / 2 + 8
        box = (cx - size / 2, cy - size / 2, cx + size / 2, cy + size / 2)
        canvas.create_arc(*box, start=135, extent=-270, style="arc", outline=COLORS["elevated"], width=self._px(13))
        canvas.create_arc(*box, start=135, extent=-270 * score / 100, style="arc", outline=color, width=self._px(13))
        canvas.create_text(cx, cy - self._px(4), text=str(score), fill=COLORS["heading"], font=self._font(30, "bold"))
        canvas.create_text(cx, cy + self._px(30), text="/ 100", fill=COLORS["muted"], font=self._font(10))
        canvas.create_text(cx, self._px(18), text=self.status.get(), fill=color, font=self._font(11, "bold"))

    def _draw_trend(self) -> None:
        canvas = self.trend_canvas
        canvas.delete("all")
        width = max(canvas.winfo_width(), 400)
        height = max(canvas.winfo_height(), 120)
        left, right, top, bottom = 30, width - 18, 20, height - 26
        for ratio in (0.0, 0.5, 1.0):
            y = bottom - (bottom - top) * ratio
            canvas.create_line(left, y, right, y, fill=COLORS["border"], dash=(2, 4))
            canvas.create_text(self._px(4), y, text=str(int(ratio * 100)), anchor="w", fill=COLORS["muted"], font=self._font(8))
        values = [score for _, score in self.health_history[-30:]] or [self._health_score(self.status.get().lower())]
        points = []
        for index, value in enumerate(values):
            x = left if len(values) == 1 else left + (right - left) * index / (len(values) - 1)
            y = bottom - (bottom - top) * value / 100
            points.extend((x, y))
        if len(points) >= 4:
            canvas.create_line(*points, fill=COLORS["cyan"], width=self._px(2), smooth=True)
        for index in range(0, len(points), 2):
            radius = self._px(3)
            canvas.create_oval(points[index] - radius, points[index + 1] - radius, points[index] + radius, points[index + 1] + radius, fill=COLORS["cyan"], outline=COLORS["card"])
        canvas.create_text(left, self._px(3), text="HEALTH SCORE", anchor="nw", fill=COLORS["muted"], font=self._font(9, "bold"))

    def _draw_checks(self, checks: list[object], overall: str, checked_at: object) -> None:
        canvas = self.health
        canvas.delete("all")
        width = max(canvas.winfo_width(), 300)
        canvas.create_text(0, self._px(4), text=f"OVERALL  {overall.upper()}   ·   {format_timestamp(checked_at)}", anchor="nw", fill=self._status_color(overall), font=self._font(9, "bold"))
        height = max(canvas.winfo_height(), 90)
        valid_checks = [item for item in checks if isinstance(item, dict)]
        line_height = max(self._px(18), min(self._px(28), (height - self._px(44)) / max(len(valid_checks), 1)))
        y = self._px(30)
        for item in valid_checks:
            status = str(item.get("status", "unknown"))
            dot = self._px(5)
            canvas.create_oval(0, y + self._px(3), dot * 2, y + self._px(3) + dot * 2, fill=self._status_color(status), outline="")
            canvas.create_text(self._px(18), y, text=f"{item.get('level', '??')}  {item.get('name', 'unknown')}", anchor="nw", fill=COLORS["text"], font=self._font(9))
            canvas.create_text(width - self._px(4), y, text=status.upper(), anchor="ne", fill=self._status_color(status), font=self._font(9, "bold"))
            y += line_height
        if not valid_checks:
            canvas.create_text(0, y, text="No readable health checks are available.", anchor="nw", fill=COLORS["muted"], font=self._font(10))

    def _canvas_metric(self, canvas: tk.Canvas, x: float, width: float, label: str, value: str, detail: str, color: str) -> None:
        top, bottom = self._px(12), self._px(112)
        inset = self._px(16)
        canvas.create_rectangle(x, top, x + width, bottom, fill=COLORS["surface"], outline=COLORS["border"], width=1)
        canvas.create_rectangle(x, top, x + self._px(4), bottom, fill=color, outline="")
        canvas.create_text(x + inset, self._px(30), text=label, anchor="w", fill=COLORS["muted"], font=self._font(9, "bold"))
        canvas.create_text(x + inset, self._px(62), text=value, anchor="w", fill=COLORS["heading"], font=self._font(20, "bold"))
        canvas.create_text(x + inset, self._px(92), text=detail, anchor="w", fill=COLORS["muted"], font=self._font(9))

    def _session_state(self, session: dict[str, str]) -> str:
        parsed = parse_timestamp(session.get("last_seen_at"))
        if parsed is None:
            return "unknown"
        age = (datetime.now(UTC) - parsed.astimezone(UTC)).total_seconds()
        return "active" if age <= 90 else "stale"

    def _draw_sessions(self) -> None:
        canvas = self.session_canvas
        canvas.delete("all")
        width = max(canvas.winfo_width(), 450)
        active = sum(1 for _, _, state in self.session_rows if state == "active")
        stale = sum(1 for _, _, state in self.session_rows if state == "stale")
        unknown = len(self.session_rows) - active - stale
        card_width = (width - 24) / 3
        self._canvas_metric(canvas, 0, card_width - 6, "接続中", str(active), "heartbeat が90秒以内", COLORS["green"])
        self._canvas_metric(canvas, card_width + 6, card_width - 6, "要確認", str(stale), "heartbeat が90秒超過", COLORS["amber"])
        self._canvas_metric(canvas, card_width * 2 + 12, card_width - 12, "状態不明", str(unknown), "時刻を読み取れません", COLORS["muted"])

    def _draw_activity(self) -> None:
        canvas = self.activity_canvas
        canvas.delete("all")
        width = max(canvas.winfo_width(), 450)
        events = self.activity_events
        ok = sum(1 for event in events if str(event.get("result", "")).lower() == "ok")
        failed = sum(1 for event in events if str(event.get("result", "")).lower() in {"failed", "error", "critical"})
        cancelled = sum(1 for event in events if str(event.get("result", "")).lower() == "cancelled")
        card_width = (width - 24) / 3
        self._canvas_metric(canvas, 0, card_width - 6, "直近イベント", str(len(events)), "最大200件を表示", COLORS["blue"])
        self._canvas_metric(canvas, card_width + 6, card_width - 6, "成功", str(ok), "result = ok", COLORS["green"])
        self._canvas_metric(canvas, card_width * 2 + 12, card_width - 12, "失敗 / 取消", str(failed + cancelled), f"失敗 {failed} / 取消 {cancelled}", COLORS["red"] if failed else COLORS["amber"])

    def _draw_incidents(self) -> None:
        canvas = self.incident_canvas
        canvas.delete("all")
        width = max(canvas.winfo_width(), 450)
        count = len(self.incident_events)
        latest = relative_time(self.incident_events[0].get("timestamp")) if self.incident_events else "記録なし"
        critical = sum(1 for event in self.incident_events if str(event.get("result", "")).lower() == "critical")
        card_width = (width - 24) / 3
        self._canvas_metric(canvas, 0, card_width - 6, "障害イベント", str(count), "現在のフィルター対象", COLORS["red"] if count else COLORS["green"])
        self._canvas_metric(canvas, card_width + 6, card_width - 6, "直近の記録", latest, "復旧状態は別途確認が必要", COLORS["amber"] if count else COLORS["green"])
        self._canvas_metric(canvas, card_width * 2 + 12, card_width - 12, "Critical", str(critical), "critical result の件数", COLORS["red"] if critical else COLORS["green"])

    def _draw_tasks(self) -> None:
        canvas = self.task_canvas
        canvas.delete("all")
        width = max(canvas.winfo_width(), 450)
        ready = sum(1 for _, status, _ in self.task_rows if status.lower() in {"ready", "running"})
        unknown = sum(1 for _, status, _ in self.task_rows if status.lower() == "unknown")
        attention = len(self.task_rows) - ready - unknown
        card_width = (width - 24) / 3
        self._canvas_metric(canvas, 0, card_width - 6, "稼働可能", str(ready), "Ready / Running", COLORS["green"])
        self._canvas_metric(canvas, card_width + 6, card_width - 6, "取得不能", str(unknown), "未登録または権限・取得の問題", COLORS["amber"] if unknown else COLORS["green"])
        self._canvas_metric(canvas, card_width * 2 + 12, card_width - 12, "要確認", str(attention), "Disabled / Queued / その他", COLORS["red"] if attention else COLORS["green"])

    def _draw_logs(self) -> None:
        canvas = self.log_canvas
        canvas.delete("all")
        width = max(canvas.winfo_width(), 450)
        errors = sum(any(token in line.lower() for token in ("error", "failed", "critical")) for line in self.log_lines)
        warnings = sum("warn" in line.lower() for line in self.log_lines)
        sources = sum(1 for line in self.log_lines if line.startswith("["))
        card_width = (width - 24) / 3
        self._canvas_metric(canvas, 0, card_width - 6, "表示行", str(len(self.log_lines)), "直近ログの抜粋", COLORS["blue"])
        self._canvas_metric(canvas, card_width + 6, card_width - 6, "警告", str(warnings), "warn を含む行", COLORS["amber"] if warnings else COLORS["green"])
        self._canvas_metric(canvas, card_width * 2 + 12, card_width - 12, "異常語", str(errors), f"ログソース {sources}件", COLORS["red"] if errors else COLORS["green"])

    def _draw_tab_visuals(self) -> None:
        if not hasattr(self, "session_canvas"):
            return
        self._draw_sessions()
        self._draw_activity()
        self._draw_incidents()
        self._draw_tasks()
        self._draw_logs()

    def _set_status(self, overall: str) -> None:
        labels = {"healthy": ("HEALTHY", COLORS["green"], "All checks passing"), "degraded": ("DEGRADED", COLORS["amber"], "Attention required"), "critical": ("CRITICAL", COLORS["red"], "Critical checks failing"), "unknown": ("UNKNOWN", COLORS["muted"], "Snapshot unavailable")}
        label, color, detail = labels.get(overall, labels["unknown"])
        self.status.set(label)
        self.status_detail.set(detail)
        self.status_label.configure(fg=color)

    def refresh(self) -> None:
        try:
            subprocess.run([os.environ.get("PYTHON", "python"), str(Path(__file__).with_name("health.py"))], timeout=4, check=False, capture_output=True)
        except (OSError, subprocess.TimeoutExpired):
            self.refresh_state.set("Health command unavailable  /  showing last snapshot")
        snapshot = read_json(SNAPSHOT)
        overall = str(snapshot.get("overall", "unknown"))
        self._set_status(overall)
        checked_at = snapshot.get("checked_at", "not available")
        self.checked.set(compact_timestamp(checked_at))
        checks = snapshot.get("checks", [])
        check_items = checks if isinstance(checks, list) else []
        self.check_statuses = {
            str(item.get("name", "")).lower(): str(item.get("status", "unknown")).lower()
            for item in check_items
            if isinstance(item, dict)
        }
        self.health_history.append((str(checked_at), self._health_score(overall)))
        self.health_history = self.health_history[-30:]
        self._draw_checks(check_items, overall, checked_at)
        self._redraw_visuals()
        activity = read_json(ACTIVITY)
        sessions = activity.get("sessions", {})
        operations = activity.get("operations", {})
        activity_readable = ACTIVITY.is_file() and isinstance(sessions, dict) and isinstance(operations, dict)
        self.session.set(str(len(sessions)) if activity_readable else "—")
        self.operations.set(str(len(operations)) if activity_readable else "—")
        self.session_rows = []
        for item in self.sessions.get_children():
            self.sessions.delete(item)
        if activity_readable:
            for session_id, raw_session in sessions.items():
                session = session_details(session_id, raw_session)
                heartbeat = session["last_seen_at"]
                state = self._session_state(session)
                self.session_rows.append((str(session_id), heartbeat, state))
                state_label = {"active": "● 接続中", "stale": "● 要確認", "unknown": "● 不明"}.get(state, "● 不明")
                user_label = session["profile_name"] or session["user_id"] or compact_id(session_id)
                if session["profile_name"] and session["user_id"]:
                    user_label = f"{session['profile_name']} / {compact_id(session['user_id'])}"
                device_label = compact_id(session["device_id"]) if session["device_id"] else "—"
                if session["connection_state"] not in {"", "connected", "unknown"}:
                    state_label = f"{state_label} / {session['connection_state']}"
                self.sessions.insert("", "end", values=(user_label, f"{relative_time(heartbeat)}  /  {format_timestamp(heartbeat)}", device_label, state_label), tags=(self._tree_status_tag(state),))
        if not activity_readable:
            self.session_rows.append(("activity-state", None, "unknown"))
            self.sessions.insert("", "end", values=("—", "activity state を読み取れません", "—", "● 不明"), tags=("unknown",))
        elif not self.session_rows:
            self.sessions.insert("", "end", values=("—", "接続中のセッションはありません", "—", "—"))
        self.activity_events = read_events()
        self.refresh_history()
        self.incident_source_events = [event for event in self.activity_events if str(event.get("result", "")).lower() in {"failed", "error", "critical"}]
        self.refresh_incidents()
        self.task_rows = read_task_status()
        for item in self.tasks.get_children():
            self.tasks.delete(item)
        for task, status, result in self.task_rows:
            status_label = {"unknown": "● 取得不能", "disabled": "● 無効"}.get(status.lower(), f"● {status}")
            self.tasks.insert("", "end", values=(task, status_label, result), tags=(self._tree_status_tag(status),))
        self.log_lines = recent_logs()
        self.set_text(self.logs, self.log_lines)
        self._draw_tab_visuals()
        self.refresh_state.set("Auto-refresh 5s  /  Last refresh " + datetime.now().astimezone().strftime("%H:%M:%S"))
        self.root.after(5000, self.refresh)

    def refresh_history(self) -> None:
        if not hasattr(self, "history"):
            return
        selected = self.history_filter.get()
        window = self.history_window_filter.get()
        user_query = self.history_user_filter.get().strip().lower()
        action_query = self.history_action_filter.get().strip().lower()
        for item in self.history.get_children():
            self.history.delete(item)
        matched = 0
        for event in self.activity_events:
            if not event_within_window(event.get("timestamp"), window):
                continue
            if selected != "all" and str(event.get("result", "")).lower() != selected:
                continue
            if user_query and user_query not in str(event.get("user_id", "")).lower():
                continue
            if action_query and action_query not in str(event.get("action", "")).lower():
                continue
            matched += 1
            result = str(event.get("result", ""))
            self.history.insert("", "end", values=(format_timestamp(event.get("timestamp")), compact_id(event.get("user_id")), event.get("action", ""), event.get("target", ""), result.upper(), compact_id(event.get("device_id")), event.get("duration_ms", "")), tags=(self._tree_status_tag(result),))
        if not self.activity_events:
            self.history.insert("", "end", values=("—", "—", "操作履歴はまだありません", "SMAI本体からの監査イベント連携後に表示されます", "—", "—", "—"))
        elif matched == 0:
            self.history.insert("", "end", values=("—", "—", "条件に一致するイベントはありません", "フィルター条件を変更して再検索してください", "—", "—", "—"))

    def _clear_history_filters(self) -> None:
        self.history_window_filter.set("24h")
        self.history_filter.set("all")
        self.history_user_filter.set("")
        self.history_action_filter.set("")
        self.refresh_history()

    def refresh_incidents(self) -> None:
        if not hasattr(self, "incidents"):
            return
        selected = self.incident_filter.get()
        window = self.incident_window_filter.get()
        self.incident_events = [
            event
            for event in self.incident_source_events
            if event_within_window(event.get("timestamp"), window)
            and (selected == "all" or str(event.get("result", "")).lower() == selected)
        ]
        for item in self.incidents.get_children():
            self.incidents.delete(item)
        for event in self.incident_events:
            result = str(event.get("result", ""))
            self.incidents.insert("", "end", values=(format_timestamp(event.get("timestamp")), event.get("action", ""), event.get("target", ""), result.upper()), tags=(self._tree_status_tag(result),))
        if not self.incident_source_events:
            self.incidents.insert("", "end", values=("—", "障害は記録されていません", "現在の監査イベントに failed / error / critical はありません", "OK"))
        elif not self.incident_events:
            self.incidents.insert("", "end", values=("—", "条件に一致する障害はありません", "重要度フィルターを変更して再検索してください", "—"))


def main() -> None:
    _enable_dpi_awareness()
    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    root = tk.Tk()
    Dashboard(root)
    root.mainloop()


def _enable_dpi_awareness() -> None:
    """Ask Windows for crisp per-monitor rendering when the API is available."""
    if os.name != "nt":
        return
    try:
        import ctypes

        awareness_context = ctypes.c_void_p(-4)  # PER_MONITOR_AWARE_V2
        ctypes.windll.user32.SetProcessDpiAwarenessContext(awareness_context)
    except (AttributeError, OSError):
        return


if __name__ == "__main__":
    main()
