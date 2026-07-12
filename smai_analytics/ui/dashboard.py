from __future__ import annotations

import json
import math
import os
import subprocess
import tkinter as tk
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tkinter import ttk

from ..monitoring import connection_watch, task_monitor, telemetry
from ..operations import incident_automation

try:
    from PIL import Image, ImageTk
except ImportError:  # pragma: no cover - exercised on minimal Python installs
    Image = None
    ImageTk = None

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = Path(os.environ.get("SMAI_PROJECT_ROOT", r"C:\Users\user\workspace\SMAI_Projects\Smart_Market_AI"))
RUNTIME_ROOT = Path(os.environ.get("SMAI_RUNTIME_ROOT", r"C:\Users\user\workspace\SMAI_Projects\SMAI_Server_Runtime"))
SNAPSHOT = PROJECT_ROOT / "data/ops/server_ops/health_snapshot.json"
ACTIVITY = PROJECT_ROOT / "data/ops/server_ops/activity_state.json"
EVENT_LOG = RUNTIME_ROOT / "audit/events.jsonl"
CONNECTION_WATCH_STATE = RUNTIME_ROOT / "connections/watch_state.json"
BACKUP_SMOKE_STATE = RUNTIME_ROOT / "backup_restore_smoke.json"
LOG_ROOTS = (RUNTIME_ROOT / "logs", PROJECT_ROOT / "logs/server_ops", PROJECT_ROOT / "logs/maintenance")
ASSET_ROOT = REPOSITORY_ROOT / "assets"
ANALYTICS_LOGO = ASSET_ROOT / "smai-analytics-logo-transparent.png"
ANALYTICS_MASCOT = ASSET_ROOT / "smai-analytics-mascot.png"
ANALYTICS_WORDMARK = ASSET_ROOT / "smai-analytics-wordmark-luminous.png"
TOPOLOGY_SPRITE = ASSET_ROOT / "smai-topology-devices.png"
TOPOLOGY_SMARTPHONE = ASSET_ROOT / "smai-topology-smartphone-v1.png"
TOPOLOGY_TABLET = ASSET_ROOT / "smai-topology-tablet-v1.png"
TASKS = (
    "SMAI-Server-Analytics",
    "SmartMarketAI-Server-Autostart",
    "SmartMarketAI-Server-Watch",
    "SmartMarketAI-Symbol-Maintenance-IfDue",
    "SMAI-Incident-Automation",
)


def expected_task_root(task: str) -> Path:
    return (
        REPOSITORY_ROOT
        if task in {"SMAI-Server-Analytics", "SMAI-Incident-Automation"}
        else PROJECT_ROOT
    )


def task_path_status(task: str, task_xml: str) -> str:
    """Return a fail-closed status when a scheduled task points at an old workspace."""

    expected = str(expected_task_root(task)).replace("/", "\\").casefold()
    configured = task_xml.replace("/", "\\").casefold()
    return "ready" if expected in configured else "path mismatch"

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

TIME_WINDOW_OPTIONS = ("過去24時間", "過去7日間", "過去30日間", "すべて")
TIME_WINDOW_KEYS = {
    "過去24時間": "24h",
    "過去7日間": "7d",
    "過去30日間": "30d",
    "すべて": "all",
}
HISTORY_RESULT_OPTIONS = ("すべて", "成功", "失敗", "取り消し")
INCIDENT_SEVERITY_OPTIONS = ("すべて", "失敗", "エラー", "重大")
RESULT_FILTER_KEYS = {
    "すべて": "all",
    "成功": "ok",
    "失敗": "failed",
    "取り消し": "cancelled",
    "エラー": "error",
    "重大": "critical",
}
CLIENT_TYPES = ("desktop", "smartphone", "tablet")
CLIENT_TYPE_LABELS = {
    "desktop": "PC",
    "smartphone": "スマートフォン",
    "tablet": "タブレット",
    "unknown": "種別不明",
}
CLIENT_HEARTBEAT_SECONDS = 90
STATUS_PRIORITY = {
    "critical": 5,
    "error": 5,
    "failed": 5,
    "degraded": 4,
    "stale": 4,
    "unknown": 3,
    "healthy": 1,
    "ok": 1,
    "active": 1,
    "running": 1,
}


def time_window_key(value: object) -> str:
    """Translate the concise Japanese UI label into the stable filter key."""

    return TIME_WINDOW_KEYS.get(str(value), str(value))


def result_filter_key(value: object) -> str:
    """Translate a UI result label without coupling storage values to the UI."""

    return RESULT_FILTER_KEYS.get(str(value), str(value))


def telemetry_window(value: object) -> timedelta:
    return {
        "24h": timedelta(hours=24),
        "7d": timedelta(days=7),
        "30d": timedelta(days=30),
    }.get(time_window_key(value), timedelta(hours=24))


def client_type(value: object) -> str:
    """Map the privacy-safe session category to a topology client node."""

    normalized = str(value or "").strip().casefold()
    if normalized in {"tablet", "ipad"} or "tablet" in normalized:
        return "tablet"
    if normalized in {"smartphone", "phone", "mobile", "iphone", "android"}:
        return "smartphone"
    if normalized in {"desktop", "pc", "windows", "macos", "linux", "web"}:
        return "desktop"
    return "unknown"


def heartbeat_state(value: object, *, now: datetime | None = None) -> str:
    """Classify the freshness of one client heartbeat without assuming success."""

    parsed = parse_timestamp(value)
    if parsed is None:
        return "unknown"
    current = (now or datetime.now(UTC)).astimezone(UTC)
    age = (current - parsed.astimezone(UTC)).total_seconds()
    return "active" if age <= CLIENT_HEARTBEAT_SECONDS else "stale"


def session_connection_status(session: dict[str, str], *, now: datetime | None = None) -> str:
    """Use explicit disconnect evidence first, then the last received heartbeat."""

    connection = str(session.get("connection_state") or "").strip().casefold()
    if connection in {"critical", "failed", "error"}:
        return "critical"
    if connection in {"degraded", "disconnected", "offline", "closed", "stale"}:
        return "degraded"
    state = heartbeat_state(session.get("last_seen_at"), now=now)
    return "ok" if state == "active" else "degraded" if state == "stale" else "unknown"


def worst_status(*statuses: str) -> str:
    """Return the most cautious status, keeping absent evidence as unknown."""

    return max(statuses or ("unknown",), key=lambda item: STATUS_PRIORITY.get(item.lower(), 3))


def client_connection_status(
    sessions: list[dict[str, str]],
    requested_type: str,
    *,
    activity_readable: bool,
    now: datetime | None = None,
) -> str:
    """Resolve one client category only from readable, category-specific evidence."""

    if not activity_readable:
        return "unknown"
    matching = [session_connection_status(session, now=now) for session in sessions if session.get("client_type") == requested_type]
    return worst_status(*matching) if matching else "unknown"


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
        raw_client_type = value.get("client_type") or value.get("device_type") or value.get("platform")
        return {
            "session_id": str(session_id),
            "last_seen_at": str(value.get("last_seen_at") or ""),
            "user_id": str(value.get("user_id") or ""),
            "profile_name": str(value.get("profile_name") or ""),
            "device_id": str(value.get("device_id") or ""),
            "platform": str(value.get("platform") or ""),
            "client_type": client_type(raw_client_type),
            "connection_state": str(value.get("connection_state") or "unknown"),
        }
    return {
        "session_id": str(session_id),
        "last_seen_at": str(value or ""),
        "user_id": "",
        "profile_name": "",
        "device_id": "",
        "platform": "",
        "client_type": "unknown",
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


def read_task_status() -> list[dict[str, str]]:
    """Collect task freshness from Scheduler plus the local restore smoke record."""

    return task_monitor.collect(
        TASKS,
        runtime_root=RUNTIME_ROOT,
        expected_root=expected_task_root,
        backup_state=read_json(BACKUP_SMOKE_STATE),
    )


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


def format_bytes(value: object) -> str:
    try:
        size = max(0, int(value))
    except (TypeError, ValueError):
        return "—"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{size} B"
        size /= 1024
    return "—"


def ui_scale_for_display(width: int, height: int) -> float:
    """Return a conservative content scale for large desktop displays.

    Tk's DPI scaling keeps fonts sharp, but it intentionally does not make a
    9pt operations console more legible just because there are twice as many
    pixels available.  This scale handles that layout decision separately.
    """

    desktop_scale = max(width / 1920, height / 1080)
    return max(1.0, min(1.65, desktop_scale))


def layout_mode_for_window(
    width: int,
    height: int,
    screen_width: int,
    screen_height: int,
    *,
    layout_scale: float = 1.0,
) -> tuple[bool, bool]:
    """Return ``(compact, narrow)`` from the usable window dimensions.

    Windows already reports Tk window geometry in the desktop coordinate
    system for the active monitor.  Applying the DPI scale to the breakpoints
    a second time made a normal 4K desktop look like a narrow notebook and
    replaced its complete navigation and branded header with the micro UI.
    DPI is still used for fonts, padding, and canvas sizes; reflow itself is
    reserved for windows that are genuinely short or narrow.
    """

    del screen_width, screen_height, layout_scale
    compact = width < 1180 or height < 680
    narrow = width < 1080
    return compact, narrow


def micro_layout_for_window(width: int, height: int, *, layout_scale: float = 1.0) -> bool:
    """Return whether the console needs its single-column safety layout.

    This profile is deliberately based on the window, not just the monitor.
    A user can resize a dashboard on a large display to a narrow working area;
    fixed-width cards and tab captions must still stay separate in that case.
    """

    del layout_scale
    # A short window can use its page scrollbar; reserve the stronger micro
    # transformations for genuinely constrained working areas.  This keeps
    # the complete tab names, header assets, and three KPI cards available on
    # ordinary 1080p and 4K monitors at any Windows DPI setting.
    return width < 720 or height <= 520


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
        # Point fonts already follow Tk's per-monitor DPI setting.  Pixel
        # dimensions do not, so scale card heights and padding separately to
        # keep text inside its card at 125%/150%/200% Windows scaling.
        self.content_scale = ui_scale_for_display(self.root.winfo_screenwidth(), self.root.winfo_screenheight())
        self.layout_scale = max(self.content_scale, self.ui_scale / (96 / 72))
        self.compact_layout = False
        self.narrow_layout = False
        self.micro_layout = False
        self._last_layout_size: tuple[int, int] | None = None
        self.scrollable_tab_canvases: dict[str, tk.Canvas] = {}
        self._layout_ready = False
        self.root.configure(bg=COLORS["page"])
        self.status = tk.StringVar(value="CHECKING")
        self.status_detail = tk.StringVar(value="Collecting server health")
        self.session = tk.StringVar(value="-")
        self.operations = tk.StringVar(value="-")
        self.checked = tk.StringVar(value="-")
        self.checked_summary = tk.StringVar(value="最終確認 —")
        self.refresh_state = tk.StringVar(value="Auto-refresh 5s")
        self.health_history: list[tuple[str, int]] = []
        self.health_rollups: list[dict[str, object]] = []
        self.trends_window_filter = tk.StringVar(value="過去24時間")
        self.backup_smoke: dict[str, object] = {}
        self.latest_storage: list[dict[str, object]] = []
        self.session_rows: list[tuple[str, object, str]] = []
        self.client_sessions: list[dict[str, str]] = []
        self.current_connection_counts = {client_type: 0 for client_type in connection_watch.CLIENT_TYPES}
        self.current_unlinked_counts = {client_type: 0 for client_type in connection_watch.CLIENT_TYPES}
        self.connection_watch: dict[str, object] = {"ok": True, "available": False, "state": {}, "reason": "not started"}
        self.activity_readable = False
        self.activity_events: list[dict[str, object]] = []
        self.incident_events: list[dict[str, object]] = []
        self.incident_source_events: list[dict[str, object]] = []
        self.task_rows: list[dict[str, str]] = []
        self.task_observations: list[dict[str, object]] = []
        self.log_lines: list[str] = []
        self.flow_phase = 0
        self.logo_image = self._load_brand_image(ANALYTICS_LOGO, max_width=48, max_height=48)
        self.mascot_image = self._load_brand_image(ANALYTICS_MASCOT, max_width=108, max_height=108)
        self.wordmark_shield_image, self.wordmark_lettering_image = self._load_wordmark_parts(
            ANALYTICS_WORDMARK,
            shield_height=88,
            lettering_height=70,
        )
        self.topology_images = {
            "SMAI UI": self._load_sprite_tile(TOPOLOGY_SPRITE, 0, max_width=60, max_height=60),
            "Streamlit": self._load_sprite_tile(TOPOLOGY_SPRITE, 1, max_width=60, max_height=60),
            "Runtime": self._load_sprite_tile(TOPOLOGY_SPRITE, 2, max_width=60, max_height=60),
            "Analytics": self._load_sprite_tile(TOPOLOGY_SPRITE, 3, max_width=60, max_height=60),
        }
        self.check_statuses: dict[str, str] = {}
        self._configure_style()
        self._build()
        self.root.bind("<Configure>", self._on_root_configure, add="+")
        self.root.after_idle(self._sync_layout_density)
        self.refresh()
        self._animate_topology()

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

    def _on_root_configure(self, event: tk.Event[tk.Misc]) -> None:
        """Use a denser hierarchy when a PC window has limited height."""

        if event.widget != self.root:
            return
        self._apply_layout_density(event.width, event.height)

    def _sync_layout_density(self) -> None:
        self._apply_layout_density(self.root.winfo_width(), self.root.winfo_height())

    def _apply_layout_density(self, width: int, height: int) -> None:
        """Reflow the dashboard before a small window can clip its labels."""

        screen_width = max(1, self.root.winfo_screenwidth())
        screen_height = max(1, self.root.winfo_screenheight())
        compact, narrow = layout_mode_for_window(
            width,
            height,
            screen_width,
            screen_height,
            layout_scale=self.layout_scale,
        )
        micro = micro_layout_for_window(width, height, layout_scale=self.layout_scale)
        if self._layout_ready and self._last_layout_size == (width, height):
            return
        profile_changed = (
            not self._layout_ready
            or compact != self.compact_layout
            or narrow != self.narrow_layout
            or micro != self.micro_layout
        )
        self.compact_layout = compact
        self.narrow_layout = narrow
        self.micro_layout = micro
        self._last_layout_size = (width, height)
        self.outer.configure(padding=(self._px(8 if micro else 18), self._px(6 if micro else 8)))
        self._layout_header(narrow, micro, width)
        self._layout_facts(narrow, compact, micro)
        self._layout_overview(narrow, compact, micro)
        self._layout_trends(narrow, compact, micro, width)
        self._layout_notebook_tabs(narrow, micro)
        self._layout_filter_controls(narrow, micro)
        self._layout_table_bodies(micro)
        self._layout_panel_headers(narrow)
        self._layout_footer(narrow)
        for canvas in self._summary_canvases:
            canvas.configure(height=self._px(112 if micro else 64 if compact else 84))
        wrap_width = max(self._px(220), width - self._px(40))
        self.connection_total_summary_label.configure(wraplength=wrap_width)
        self.report_summary_label.configure(wraplength=wrap_width)
        # Keep the visual identity on every desktop profile.  Only the truly
        # constrained micro profile substitutes a text-only compact mark.
        if profile_changed:
            self._resize_brand_images(micro)
            self._resize_topology_images(compact or micro)
        self._layout_ready = True
        self.root.after_idle(self._redraw_visuals)
        self.root.after_idle(self._draw_tab_visuals)
        self.root.after_idle(self._refresh_overview_scrollregion)
        self.root.after_idle(self._refresh_trends_scrollregion)

    def _layout_header(self, narrow: bool, micro: bool, width: int) -> None:
        """Stack brand and status blocks when the header no longer fits."""

        self.brand_block.pack_forget()
        self.status_block.pack_forget()
        self.status_label.pack_forget()
        self.status_detail_label.pack_forget()
        self.status_checked_label.pack_forget()
        if self.wordmark_block is not None:
            self.wordmark_block.pack_forget()
        self.compact_brand_label.pack_forget()
        self.brand_tagline.pack_forget()
        self.compact_brand_label.configure(font=self._font(16 if micro else 20, "bold"))
        self.status_label.configure(
            font=self._font(10 if micro else 11, "bold"),
            padx=self._px(10 if micro else 16),
            pady=self._px(4 if micro else 8),
        )
        if micro:
            if self.wordmark_block is not None:
                self.compact_brand_label.pack(anchor="w")
            self.brand_block.pack(side="left", anchor="nw")
            self.status_block.pack(side="right", anchor="ne")
            self.status_label.pack(anchor="e")
            self.status_detail_label.configure(
                anchor="e",
                justify="right",
                wraplength=max(self._px(180), width - self._px(210)),
            )
            self.status_detail_label.pack(anchor="e", pady=(self._px(3), 0))
            self.status_checked_label.pack(anchor="e", pady=(self._px(2), 0))
        elif narrow:
            # A normal laptop/monitor can still show the complete brand.  Put
            # the live status below it before removing useful visual context.
            if self.wordmark_block is not None:
                self.wordmark_block.pack(anchor="w")
            self.brand_tagline.pack(anchor="w", pady=(self._px(2), 0))
            self.brand_block.pack(fill="x", anchor="w")
            self.status_block.pack(fill="x", anchor="w", pady=(self._px(5 if micro else 8), 0))
            self.status_label.pack(anchor="w")
            self.status_detail_label.configure(
                anchor="w",
                justify="left",
                wraplength=max(self._px(180), width - self._px(32 if micro else 48)),
            )
            self.status_detail_label.pack(anchor="w", pady=(self._px(3 if micro else 5), 0))
            self.status_checked_label.pack(anchor="w", pady=(self._px(2), 0))
        else:
            if self.wordmark_block is not None:
                # ``brand_tagline`` has just been pack_forget() above.  Tk
                # rejects it as a ``before`` target, which previously aborted
                # all remaining layout work and left the header blank.
                self.wordmark_block.pack(anchor="w")
            self.brand_tagline.pack(anchor="w", pady=(self._px(2), 0))
            self.brand_block.pack(side="left", anchor="w")
            self.status_block.pack(side="right", anchor="ne")
            self.status_label.pack(anchor="e")
            self.status_detail_label.configure(anchor="e", justify="right", wraplength=0)
            self.status_detail_label.pack(anchor="e", pady=(self._px(5), 0))
            self.status_checked_label.pack(anchor="e", pady=(self._px(2), 0))

    def _layout_facts(self, narrow: bool, compact: bool, micro: bool) -> None:
        """Keep KPI text readable by using a second row before it can crowd."""

        for index in range(3):
            self.facts.columnconfigure(index, weight=0, uniform="")
            self.facts.rowconfigure(index, weight=0)
        for card in self.fact_cards:
            card.grid_forget()
        for meta_label in self.fact_meta_labels:
            meta_label.pack_forget()
            if not micro:
                meta_label.pack(anchor="w")
        if micro:
            self.facts.columnconfigure(0, weight=1, uniform="kpi")
            for index, card in enumerate(self.fact_cards):
                card.grid(row=index, column=0, sticky="nsew", pady=(0, self._px(6)) if index < len(self.fact_cards) - 1 else 0)
                self.facts.rowconfigure(index, weight=1)
            rows = len(self.fact_cards)
        elif narrow:
            for index in range(2):
                self.facts.columnconfigure(index, weight=1, uniform="kpi")
            self.facts.rowconfigure(0, weight=1)
            self.facts.rowconfigure(1, weight=1)
            for index, card in enumerate(self.fact_cards[:2]):
                card.grid(row=0, column=index, sticky="nsew", padx=(0, self._px(8)) if index < 2 else 0)
            self.fact_cards[2].grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(self._px(8), 0))
            rows = 2
        else:
            for index in range(3):
                self.facts.columnconfigure(index, weight=1, uniform="kpi")
            for index, card in enumerate(self.fact_cards):
                card.grid(row=0, column=index, sticky="nsew", padx=(0, self._px(12)) if index < 2 else 0)
            rows = 1
        card_height = 60 if micro else 60 if (compact or narrow) else 76
        self.facts.configure(height=self._px(card_height * rows + (self._px(8) if rows > 1 else 0)))

    def _layout_overview(self, narrow: bool, compact: bool, micro: bool) -> None:
        """Preserve every Overview diagnostic, using its vertical scrollbar."""

        self.map_panel.grid_forget()
        self.trend_panel.grid_forget()
        self.overview_summary.grid_forget()
        self.gauge_panel.grid_forget()
        self.checks_panel.grid_forget()
        self.recovery_panel.grid_forget()
        if narrow:
            self.overview.columnconfigure(0, weight=1, minsize=0)
            self.overview.columnconfigure(1, weight=0, minsize=0)
            for row in range(4):
                self.overview.rowconfigure(row, weight=0, minsize=0)
            self.map_panel.grid(row=0, column=0, sticky="nsew", pady=(0, self._px(10)))
            self.trend_panel.grid(row=1, column=0, sticky="nsew", pady=(0, self._px(10)))
            self.overview_summary.grid(row=2, column=0, sticky="nsew")
            self.recovery_panel.grid(row=3, column=0, sticky="nsew", pady=(self._px(8), 0))
            self.overview_summary.columnconfigure(0, weight=1, uniform="")
            self.overview_summary.columnconfigure(1, weight=0, uniform="")
            self.overview_summary.rowconfigure(0, weight=0)
            self.overview_summary.rowconfigure(1, weight=0)
            self.gauge_panel.grid(row=0, column=0, sticky="nsew", pady=(0, self._px(8)))
            self.checks_panel.grid(row=1, column=0, sticky="nsew")
            heights = (
                (self.map_canvas, 180 if micro else 220 if compact else 270),
                (self.trend_canvas, 142 if micro else 170 if compact else 210),
                (self.gauge_canvas, 128 if micro else 145),
                (self.health, 154 if micro else 180),
                (self.recovery_canvas, 112 if micro else 104),
            )
        else:
            self.overview.columnconfigure(0, weight=4, minsize=self._px(320))
            self.overview.columnconfigure(1, weight=7, minsize=self._px(520))
            self.overview.rowconfigure(0, weight=4)
            self.overview.rowconfigure(1, weight=1)
            self.overview.rowconfigure(2, weight=1)
            self.map_panel.grid(row=0, column=0, rowspan=3, sticky="nsew", padx=(0, self._px(10)))
            self.trend_panel.grid(row=0, column=1, sticky="nsew", padx=(self._px(10), 0), pady=(0, self._px(8)))
            self.overview_summary.grid(row=1, column=1, sticky="nsew", padx=(self._px(10), 0), pady=(self._px(8), 0))
            self.recovery_panel.grid(row=2, column=1, sticky="nsew", padx=(self._px(10), 0), pady=(self._px(8), 0))
            self.overview_summary.columnconfigure(0, weight=1, uniform="overview_summary")
            self.overview_summary.columnconfigure(1, weight=1, uniform="overview_summary")
            self.overview_summary.rowconfigure(0, weight=1)
            self.gauge_panel.grid(row=0, column=0, sticky="nsew", padx=(0, self._px(8)))
            self.checks_panel.grid(row=0, column=1, sticky="nsew", padx=(self._px(8), 0))
            heights = (
                (self.map_canvas, 230 if compact else 300),
                (self.trend_canvas, 180 if compact else 230),
                (self.gauge_canvas, 128),
                (self.health, 128),
                (self.recovery_canvas, 104),
            )
        for canvas, canvas_height in heights:
            canvas.configure(height=self._px(canvas_height))

    def _layout_trends(self, narrow: bool, compact: bool, micro: bool, width: int) -> None:
        """Keep longer-term charts legible on narrow and high-DPI screens."""

        if not hasattr(self, "trends_lower"):
            return
        self.latency_panel.grid_forget()
        self.capacity_panel.grid_forget()
        if narrow:
            self.trends_lower.columnconfigure(0, weight=1, uniform="")
            self.trends_lower.columnconfigure(1, weight=0, uniform="")
            self.latency_panel.grid(row=0, column=0, sticky="nsew", pady=(0, self._px(8)))
            self.capacity_panel.grid(row=1, column=0, sticky="nsew")
            latency_height = capacity_height = 96 if micro else 108 if compact else 124
            task_height = 120 if micro else 138 if compact else 156
        else:
            self.trends_lower.columnconfigure(0, weight=1, uniform="trend_lower")
            self.trends_lower.columnconfigure(1, weight=1, uniform="trend_lower")
            self.latency_panel.grid(row=0, column=0, sticky="nsew", padx=(0, self._px(4)))
            self.capacity_panel.grid(row=0, column=1, sticky="nsew", padx=(self._px(4), 0))
            latency_height = capacity_height = 135 if compact else 170
            task_height = 138 if compact else 156
        self.status_history_canvas.configure(height=self._px(150 if micro else 180 if compact else 220))
        self.latency_canvas.configure(height=self._px(latency_height))
        self.capacity_canvas.configure(height=self._px(capacity_height))
        self.task_trend_canvas.configure(height=self._px(task_height))
        self._layout_trends_controls(micro, width)

    def _layout_trends_controls(self, micro: bool, width: int) -> None:
        """Keep the time selector and telemetry coverage from sharing a row."""

        if not hasattr(self, "trends_filter_group"):
            return
        self.trends_filter_group.pack_forget()
        self.trends_summary_label.pack_forget()
        if micro:
            self.trends_filter_group.pack(anchor="w")
            self.trends_summary_label.configure(
                anchor="w",
                justify="left",
                wraplength=max(self._px(220), width - self._px(40)),
            )
            self.trends_summary_label.pack(fill="x", anchor="w", pady=(self._px(5), 0))
        else:
            self.trends_filter_group.pack(side="left")
            self.trends_summary_label.configure(anchor="e", justify="right", wraplength=0)
            self.trends_summary_label.pack(side="right")

    def _layout_notebook_tabs(self, narrow: bool, micro: bool) -> None:
        """Keep every operational screen reachable on a narrow notebook."""

        if not hasattr(self, "notebook_tab_labels"):
            return
        tab_padding = (self._px(5 if micro else 9 if narrow else 16), self._px(5 if micro else 7))
        self.style.configure(
            "TNotebook.Tab",
            padding=tab_padding,
            font=self._font(8 if micro else 9 if narrow else 10, "bold"),
        )
        for page, full_label, compact_label, micro_label in self.notebook_tab_labels:
            self.notebook.tab(page, text=micro_label if micro else compact_label if narrow else full_label)

    @staticmethod
    def _grid_groups(groups: tuple[ttk.Frame, ...], placements: tuple[tuple[int, int, int], ...]) -> None:
        for group in groups:
            group.grid_forget()
        for group, (row, column, columnspan) in zip(groups, placements):
            group.grid(row=row, column=column, columnspan=columnspan, sticky="ew", padx=(0, 8), pady=(0, 6))

    def _layout_filter_controls(self, narrow: bool, micro: bool) -> None:
        """Wrap filter fields as groups so labels and inputs remain paired."""

        for frame in (self.history_controls, self.incident_controls):
            for column in range(6):
                frame.columnconfigure(column, weight=0)
            for row in range(3):
                frame.rowconfigure(row, weight=0)
        if micro:
            self.history_controls.columnconfigure(0, weight=1)
            self.incident_controls.columnconfigure(0, weight=1)
            self._grid_groups(
                self.history_control_groups,
                tuple((index, 0, 1) for index in range(len(self.history_control_groups))),
            )
            self._grid_groups(
                self.incident_control_groups,
                tuple((index, 0, 1) for index in range(len(self.incident_control_groups))),
            )
        elif narrow:
            self.history_controls.columnconfigure(0, weight=1)
            self.history_controls.columnconfigure(1, weight=1)
            self.history_controls.columnconfigure(2, weight=0)
            self._grid_groups(
                self.history_control_groups,
                ((0, 0, 1), (0, 1, 1), (1, 0, 1), (1, 1, 2), (0, 2, 1), (2, 0, 3)),
            )
            self.incident_controls.columnconfigure(0, weight=1)
            self.incident_controls.columnconfigure(1, weight=1)
            self._grid_groups(
                self.incident_control_groups,
                ((0, 0, 1), (0, 1, 1), (0, 2, 1), (1, 0, 3)),
            )
        else:
            self._grid_groups(
                self.history_control_groups,
                tuple((0, index, 1) for index in range(len(self.history_control_groups))),
            )
            self._grid_groups(
                self.incident_control_groups,
                tuple((0, index, 1) for index in range(len(self.incident_control_groups))),
            )

    def _layout_table_bodies(self, micro: bool) -> None:
        """Give tables a concrete viewport inside a scrollable tab page."""

        if not hasattr(self, "tree_bodies"):
            return
        for tree in self.operation_trees:
            tree.configure(height=5 if micro else 12)
        for body in self.tree_bodies:
            # The Treeview's requested number of rows defines the canvas
            # content height.  Keeping geometry propagation enabled lets Tk
            # allocate those rows instead of collapsing a grid cell to zero.
            body.grid_propagate(True)
        if hasattr(self, "log_body"):
            self.log_body.grid_propagate(True)

    def _layout_panel_headers(self, narrow: bool) -> None:
        for subtitle in self.panel_subtitles:
            subtitle.pack_forget()
            if not narrow:
                subtitle.pack(side="right")

    def _layout_footer(self, narrow: bool) -> None:
        self.footer_context_label.pack_forget()
        self.footer_refresh_label.pack_forget()
        if narrow:
            self.footer_refresh_label.pack(anchor="w")
        else:
            self.footer_context_label.pack(side="left")
            self.footer_refresh_label.pack(side="right")

    def _scrollable_overview(self, parent: ttk.Frame) -> ttk.Frame:
        """Create a vertically scrollable Overview without scrolling tables."""

        canvas = tk.Canvas(parent, bg=COLORS["surface"], highlightthickness=0, bd=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        content = ttk.Frame(canvas, style="Surface.TFrame", padding=self._px(16))
        window_id = canvas.create_window((0, 0), window=content, anchor="nw")

        def update_region(_event: tk.Event[tk.Misc]) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def fit_content(event: tk.Event[tk.Misc]) -> None:
            canvas.itemconfigure(window_id, width=event.width)

        content.bind("<Configure>", update_region)
        canvas.bind("<Configure>", fit_content)
        canvas.bind("<MouseWheel>", self._scroll_overview)
        self.overview_scroll_canvas = canvas
        return content

    def _scroll_overview(self, event: tk.Event[tk.Misc]) -> str:
        """Offer wheel scrolling when the pointer is over the Overview canvas."""

        if hasattr(self, "notebook") and self.notebook.select() == str(self.overview_page):
            delta = getattr(event, "delta", 0)
            if delta:
                self.overview_scroll_canvas.yview_scroll(-max(1, abs(delta) // 120) if delta > 0 else max(1, abs(delta) // 120), "units")
                return "break"
        return ""

    def _refresh_overview_scrollregion(self) -> None:
        if hasattr(self, "overview_scroll_canvas"):
            self.overview_scroll_canvas.configure(scrollregion=self.overview_scroll_canvas.bbox("all"))

    def _scrollable_trends(self, parent: ttk.Frame) -> ttk.Frame:
        """Create a scrollable Trends page so lower charts stay reachable."""

        canvas = tk.Canvas(parent, bg=COLORS["surface"], highlightthickness=0, bd=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        content = ttk.Frame(canvas, style="Surface.TFrame", padding=self._px(16))
        window_id = canvas.create_window((0, 0), window=content, anchor="nw")

        def update_region(_event: tk.Event[tk.Misc]) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def fit_content(event: tk.Event[tk.Misc]) -> None:
            canvas.itemconfigure(window_id, width=event.width)

        content.bind("<Configure>", update_region)
        canvas.bind("<Configure>", fit_content)
        canvas.bind("<MouseWheel>", self._scroll_trends)
        self.trends_scroll_canvas = canvas
        return content

    def _scroll_trends(self, event: tk.Event[tk.Misc]) -> str:
        if hasattr(self, "notebook") and self.notebook.select() == str(self.trends_page):
            delta = getattr(event, "delta", 0)
            if delta:
                self.trends_scroll_canvas.yview_scroll(-max(1, abs(delta) // 120) if delta > 0 else max(1, abs(delta) // 120), "units")
                return "break"
        return ""

    def _refresh_trends_scrollregion(self) -> None:
        if hasattr(self, "trends_scroll_canvas"):
            self.trends_scroll_canvas.configure(scrollregion=self.trends_scroll_canvas.bbox("all"))

    def _scrollable_tab(self, parent: ttk.Frame) -> ttk.Frame:
        """Provide a real vertical viewport for data-heavy operational tabs.

        Tables retain their own row scrollbars.  This outer scrollbar is only
        for reaching a page's summary and controls when a short window cannot
        display the whole vertical hierarchy at once.
        """

        canvas = tk.Canvas(parent, bg=COLORS["surface"], highlightthickness=0, bd=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        content = ttk.Frame(canvas, style="Surface.TFrame", padding=self._px(16))
        window_id = canvas.create_window((0, 0), window=content, anchor="nw")

        def update_region(_event: tk.Event[tk.Misc]) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def fit_content(event: tk.Event[tk.Misc]) -> None:
            canvas.itemconfigure(window_id, width=event.width)

        def scroll(event: tk.Event[tk.Misc]) -> str:
            delta = getattr(event, "delta", 0)
            if delta:
                canvas.yview_scroll(-max(1, abs(delta) // 120) if delta > 0 else max(1, abs(delta) // 120), "units")
                return "break"
            return ""

        content.bind("<Configure>", update_region)
        canvas.bind("<Configure>", fit_content)
        canvas.bind("<MouseWheel>", scroll)
        content.bind("<MouseWheel>", scroll)
        self.scrollable_tab_canvases[str(parent)] = canvas
        return content

    def _resize_brand_images(self, compact: bool) -> None:
        """Keep the header recognisable without letting it consume a short window."""

        if self.wordmark_shield_label is not None and self.wordmark_lettering_label is not None:
            self.wordmark_shield_image, self.wordmark_lettering_image = self._load_wordmark_parts(
                ANALYTICS_WORDMARK,
                shield_height=66 if compact else 88,
                lettering_height=52 if compact else 70,
            )
            if self.wordmark_shield_image is not None and self.wordmark_lettering_image is not None:
                self.wordmark_shield_label.configure(image=self.wordmark_shield_image)
                self.wordmark_lettering_label.configure(image=self.wordmark_lettering_image)
        if self.mascot_label is not None:
            if compact:
                self.mascot_label.pack_forget()
                return
            self.mascot_image = self._load_brand_image(
                ANALYTICS_MASCOT,
                max_width=76 if compact else 108,
                max_height=76 if compact else 108,
            )
            if self.mascot_image is not None:
                self.mascot_label.configure(image=self.mascot_image)
                self.mascot_label.pack(side="left", padx=(0, 12), before=self.status_text)

    def _resize_topology_images(self, compact: bool) -> None:
        """Scale the decorative device icons with the compact topology."""

        icon_size = 40 if compact else 60
        self.topology_images = {
            "SMAI UI": self._load_sprite_tile(TOPOLOGY_SPRITE, 0, max_width=icon_size, max_height=icon_size),
            "Streamlit": self._load_sprite_tile(TOPOLOGY_SPRITE, 1, max_width=icon_size, max_height=icon_size),
            "Runtime": self._load_sprite_tile(TOPOLOGY_SPRITE, 2, max_width=icon_size, max_height=icon_size),
            "Analytics": self._load_sprite_tile(TOPOLOGY_SPRITE, 3, max_width=icon_size, max_height=icon_size),
            "スマートフォン": self._load_brand_image(
                TOPOLOGY_SMARTPHONE,
                max_width=26 if compact else 38,
                max_height=42 if compact else 60,
            ),
            "タブレット": self._load_brand_image(
                TOPOLOGY_TABLET,
                max_width=42 if compact else 60,
                max_height=28 if compact else 40,
            ),
        }

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
                    bounds = self._visible_bounds(source)
                    if bounds is not None:
                        source = source.crop(bounds)
                    scale = min(max_width / source.width, max_height / source.height, 1.0)
                    size = (max(1, round(source.width * scale)), max(1, round(source.height * scale)))
                    return ImageTk.PhotoImage(source.resize(size, Image.Resampling.LANCZOS))
            fallback_path = path.with_name(f"{path.stem}-header{path.suffix}")
            image = tk.PhotoImage(file=str(fallback_path if fallback_path.is_file() else path))
            factor = max(1, math.ceil(image.width() / max_width), math.ceil(image.height() / max_height))
            return image.subsample(factor, factor) if factor > 1 else image
        except (AttributeError, OSError, ValueError, tk.TclError):
            return None

    def _load_sprite_tile(self, path: Path, index: int, *, max_width: int, max_height: int) -> object | None:
        """Load one of four generated topology illustrations without a visible sprite sheet."""
        if Image is None or ImageTk is None or not path.is_file():
            return None
        try:
            with Image.open(path) as source:
                source = source.convert("RGBA")
                tile_width, tile_height = source.width // 2, source.height // 2
                column, row = index % 2, index // 2
                tile = source.crop((column * tile_width, row * tile_height, (column + 1) * tile_width, (row + 1) * tile_height))
                bounds = self._visible_bounds(tile)
                if bounds is not None:
                    tile = tile.crop(bounds)
                width = max(1, round(max_width * self.ui_scale))
                height = max(1, round(max_height * self.ui_scale))
                ratio = min(width / tile.width, height / tile.height, 1.0)
                tile = tile.resize((max(1, round(tile.width * ratio)), max(1, round(tile.height * ratio))), Image.Resampling.LANCZOS)
                return ImageTk.PhotoImage(tile)
        except (OSError, ValueError, tk.TclError):
            return None

    def _load_wordmark_parts(self, path: Path, *, shield_height: int, lettering_height: int) -> tuple[object | None, object | None]:
        """Keep lettering at a deliberate proportion of the shield without distortion."""
        if Image is None or ImageTk is None or not path.is_file():
            return None, None
        try:
            with Image.open(path) as source:
                source = source.convert("RGBA")
                split = self._wordmark_split(source)
                if split is None:
                    return None, None
                images: list[object] = []
                for crop, desired_height in ((source.crop((0, 0, split, source.height)), shield_height), (source.crop((split, 0, source.width, source.height)), lettering_height)):
                    bounds = self._visible_bounds(crop)
                    if bounds is None:
                        return None, None
                    crop = crop.crop(bounds)
                    target_height = max(1, round(desired_height * self.ui_scale))
                    target_width = max(1, round(crop.width * target_height / crop.height))
                    images.append(ImageTk.PhotoImage(crop.resize((target_width, target_height), Image.Resampling.LANCZOS)))
                return images[0], images[1]
        except (OSError, ValueError, tk.TclError):
            return None, None

    @staticmethod
    def _wordmark_split(source: object) -> int | None:
        """Split between the shield and lettering at their actual transparent gap.

        A fixed percentage cut through the luminous source image's right shield
        trim, which made the trim look like a detached vertical logo fragment.
        """

        if Image is None or not hasattr(source, "getchannel") or not hasattr(source, "width"):
            return None
        alpha = source.getchannel("A")
        occupied = [False] * source.width
        values = alpha.get_flattened_data() if hasattr(alpha, "get_flattened_data") else alpha.getdata()
        for index, value in enumerate(values):
            if value >= 48:
                occupied[index % source.width] = True
        try:
            shield_start = next(index for index, value in enumerate(occupied) if value)
        except StopIteration:
            return None
        shield_end = shield_start
        while shield_end < source.width and occupied[shield_end]:
            shield_end += 1
        lettering_start = shield_end
        while lettering_start < source.width and not occupied[lettering_start]:
            lettering_start += 1
        if shield_end == shield_start or lettering_start >= source.width:
            return None
        return (shield_end + lettering_start) // 2

    @staticmethod
    def _visible_bounds(image: object) -> tuple[int, int, int, int] | None:
        """Ignore the low-alpha chroma-key fringe when fitting generated assets."""
        if Image is None or not hasattr(image, "getchannel"):
            return None
        alpha = image.getchannel("A")
        return alpha.point(lambda value: 255 if value >= 48 else 0).getbbox()

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
        # A 520×440 working area is small but still usable with the micro
        # profile.  Do not force a larger geometry that a small display cannot
        # show; the notebook, controls, and summaries reflow instead.
        min_width = max(480, int(520 / scaling))
        min_height = max(400, int(440 / scaling))
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
        # Tk scales point fonts for Windows DPI but leaves pixel geometry
        # untouched.  Scale padding, canvas heights, and card bounds by the
        # same layout factor so enlarged text stays inside its own component.
        return max(minimum, round(value * self.layout_scale))

    def _configure_style(self) -> None:
        style = ttk.Style(self.root)
        self.style = style
        style.theme_use("clam")
        style.configure("App.TFrame", background=COLORS["page"])
        style.configure("Surface.TFrame", background=COLORS["surface"])
        style.configure("Card.TFrame", background=COLORS["card"])
        style.configure("Title.TLabel", background=COLORS["page"], foreground=COLORS["heading"], font=self._font(24, "bold"))
        style.configure("Subtitle.TLabel", background=COLORS["page"], foreground=COLORS["muted"], font=self._font(11))
        style.configure("Section.TLabel", background=COLORS["surface"], foreground=COLORS["heading"], font=self._font(11, "bold"))
        style.configure("CardLabel.TLabel", background=COLORS["card"], foreground=COLORS["muted"], font=self._font(9, "bold"))
        style.configure("CardValue.TLabel", background=COLORS["card"], foreground=COLORS["heading"], font=self._font(16, "bold"))
        style.configure("CardMeta.TLabel", background=COLORS["card"], foreground=COLORS["muted"], font=self._font(10))
        style.configure("FilterMeta.TLabel", background=COLORS["surface"], foreground=COLORS["muted"], font=self._font(9))
        style.configure("TNotebook", background=COLORS["page"], borderwidth=0, tabmargins=(0, 0, 0, 0))
        style.configure("TNotebook.Tab", background=COLORS["surface"], foreground=COLORS["muted"], padding=(self._px(16), self._px(7)), borderwidth=0, font=self._font(10, "bold"))
        style.map("TNotebook.Tab", background=[("selected", COLORS["card"])], foreground=[("selected", COLORS["cyan"])], expand=[("selected", (0, 1, 0, 0))])
        style.configure("Treeview", background=COLORS["surface"], fieldbackground=COLORS["surface"], foreground=COLORS["text"], rowheight=self._px(29), borderwidth=0, font=self._font(10))
        style.configure("Treeview.Heading", background=COLORS["elevated"], foreground=COLORS["heading"], relief="flat", font=self._font(10, "bold"))
        style.map("Treeview", background=[("selected", COLORS["card_hover"])], foreground=[("selected", COLORS["heading"])])
        style.configure("TButton", background=COLORS["elevated"], foreground=COLORS["heading"], borderwidth=1, padding=(self._px(12), self._px(7)), font=self._font(10, "bold"))
        style.map("TButton", background=[("active", COLORS["card_hover"])], foreground=[("active", COLORS["cyan"])])
        style.configure("TCombobox", fieldbackground=COLORS["surface"], background=COLORS["surface"], foreground=COLORS["text"])
        style.configure("TEntry", fieldbackground=COLORS["surface"], foreground=COLORS["text"], insertcolor=COLORS["text"])

    def _build(self) -> None:
        outer = ttk.Frame(self.root, style="App.TFrame", padding=(self._px(18), self._px(8), self._px(18), self._px(8)))
        outer.pack(fill="both", expand=True)
        self.outer = outer
        self.panel_subtitles: list[ttk.Label] = []
        header = ttk.Frame(outer, style="App.TFrame")
        header.pack(fill="x", pady=(0, self._px(8)))
        self.header = header
        brand_block = ttk.Frame(header, style="App.TFrame")
        brand_block.pack(side="left")
        self.brand_block = brand_block
        self.wordmark_block: ttk.Frame | None = None
        if self.wordmark_shield_image is not None and self.wordmark_lettering_image is not None:
            mark = ttk.Frame(brand_block, style="App.TFrame")
            self.wordmark_block = mark
            mark.pack(anchor="w")
            self.wordmark_shield_label = tk.Label(mark, image=self.wordmark_shield_image, bg=COLORS["page"], bd=0, highlightthickness=0)
            self.wordmark_shield_label.pack(side="left")
            self.wordmark_lettering_label = tk.Label(mark, image=self.wordmark_lettering_image, bg=COLORS["page"], bd=0, highlightthickness=0)
            self.wordmark_lettering_label.pack(side="left", padx=(self._px(14), 0))
            self.brand_tagline = ttk.Label(brand_block, text="運用コンソール  /  常時ローカル監視", style="Subtitle.TLabel")
            self.brand_tagline.pack(anchor="w", pady=(self._px(2), 0))
        else:
            self.wordmark_shield_label = None
            self.wordmark_lettering_label = None
            if self.logo_image is not None:
                tk.Label(brand_block, image=self.logo_image, bg=COLORS["page"], bd=0, highlightthickness=0).pack(side="left", padx=(0, 12))
            title_block = ttk.Frame(brand_block, style="App.TFrame")
            title_block.pack(side="left")
            ttk.Label(title_block, text="SMAI Analytics", style="Title.TLabel").pack(anchor="w")
            self.brand_tagline = ttk.Label(title_block, text="運用コンソール  /  常時ローカル監視", style="Subtitle.TLabel")
            self.brand_tagline.pack(anchor="w", pady=(3, 0))
        self.compact_brand_label = tk.Label(
            brand_block,
            text="SMAI Analytics",
            bg=COLORS["page"],
            fg=COLORS["heading"],
            font=self._font(20, "bold"),
            bd=0,
            highlightthickness=0,
        )
        status_block = ttk.Frame(header, style="App.TFrame")
        status_block.pack(side="right", anchor="n")
        self.status_block = status_block
        if self.mascot_image is not None:
            self.mascot_label = tk.Label(status_block, image=self.mascot_image, bg=COLORS["page"], bd=0, highlightthickness=0)
            self.mascot_label.pack(side="left", padx=(0, 12))
        else:
            self.mascot_label = None
        status_text = ttk.Frame(status_block, style="App.TFrame")
        status_text.pack(side="left", anchor="n")
        self.status_text = status_text
        self.status_label = tk.Label(status_text, textvariable=self.status, bg=COLORS["elevated"], fg=COLORS["cyan"], font=self._font(11, "bold"), padx=self._px(16), pady=self._px(8))
        self.status_label.pack(anchor="e")
        self.status_detail_label = ttk.Label(status_text, textvariable=self.status_detail, style="Subtitle.TLabel")
        self.status_detail_label.pack(anchor="e", pady=(self._px(5), 0))
        self.status_checked_label = ttk.Label(status_text, textvariable=self.checked_summary, style="Subtitle.TLabel")
        self.status_checked_label.pack(anchor="e", pady=(self._px(2), 0))

        facts = ttk.Frame(outer, style="App.TFrame")
        self.facts = facts
        facts.pack(fill="x", pady=(0, self._px(8)))
        facts.pack_propagate(False)
        facts.configure(height=self._px(76))
        facts.columnconfigure(0, weight=1, uniform="kpi")
        facts.columnconfigure(1, weight=1, uniform="kpi")
        facts.columnconfigure(2, weight=1, uniform="kpi")
        self.fact_cards: list[ttk.Frame] = []
        self.fact_meta_labels: list[ttk.Label] = []
        for index, (label, variable, meta) in enumerate((("接続セッション", self.session, "現在の接続状態"), ("実行中の処理", self.operations, "進行中の処理数"), ("最終確認", self.checked, "ローカル時刻"))):
            card = ttk.Frame(facts, style="Card.TFrame", padding=(self._px(14), self._px(8)))
            card.grid(row=0, column=index, sticky="nsew", padx=(0, self._px(12) if index < 2 else 0))
            self.fact_cards.append(card)
            ttk.Label(card, text=label, style="CardLabel.TLabel").pack(anchor="w")
            ttk.Label(card, textvariable=variable, style="CardValue.TLabel").pack(anchor="w", pady=(5, 2))
            meta_label = ttk.Label(card, text=meta, style="CardMeta.TLabel")
            meta_label.pack(anchor="w")
            self.fact_meta_labels.append(meta_label)

        notebook = ttk.Notebook(outer)
        notebook.pack(fill="both", expand=True)
        self.notebook = notebook
        overview_page = ttk.Frame(notebook, style="Surface.TFrame")
        self.overview_page = overview_page
        overview = self._scrollable_overview(overview_page)
        trends_page = ttk.Frame(notebook, style="Surface.TFrame")
        self.trends_page = trends_page
        trends = self._scrollable_trends(trends_page)
        session_page, history_page, incident_page, report_page, task_page, log_page = [
            ttk.Frame(notebook, style="Surface.TFrame") for _ in range(6)
        ]
        sessions = self._scrollable_tab(session_page)
        history = self._scrollable_tab(history_page)
        incidents = self._scrollable_tab(incident_page)
        reports = self._scrollable_tab(report_page)
        tasks = self._scrollable_tab(task_page)
        logs = self._scrollable_tab(log_page)
        self.overview = overview
        self.notebook_tab_labels = (
            (overview_page, "概要", "概要", "概"),
            (trends_page, "推移", "推移", "推"),
            (session_page, "セッション", "接続", "接"),
            (history_page, "操作履歴", "履歴", "履"),
            (incident_page, "障害", "障害", "障"),
            (report_page, "改善レポート", "報告", "報"),
            (task_page, "タスク", "タスク", "任"),
            (log_page, "ログ", "ログ", "記"),
        )
        for frame, full_label, _compact_label, _micro_label in self.notebook_tab_labels:
            notebook.add(frame, text=full_label)
        # Make the service path a tall, scan-friendly sidebar.  The timeline
        # owns the primary right-hand area, while the score and check matrix
        # remain concise supporting diagnostics below it.
        overview.columnconfigure(0, weight=4, minsize=self._px(320))
        overview.columnconfigure(1, weight=7, minsize=self._px(520))
        overview.rowconfigure(0, weight=4)
        overview.rowconfigure(1, weight=1)
        overview.rowconfigure(2, weight=1)
        map_panel = self._panel(overview, "SERVICE TOPOLOGY", "接続経路と状態")
        self.map_panel = map_panel
        map_panel.grid(row=0, column=0, rowspan=3, sticky="nsew", padx=(0, self._px(10)))
        trend_panel = self._panel(overview, "HEALTH TIMELINE", "直近の状態推移")
        self.trend_panel = trend_panel
        trend_panel.grid(row=0, column=1, sticky="nsew", padx=(self._px(10), 0), pady=(0, self._px(8)))
        overview_summary = ttk.Frame(overview, style="Surface.TFrame")
        self.overview_summary = overview_summary
        overview_summary.grid(row=1, column=1, sticky="nsew", padx=(self._px(10), 0), pady=(self._px(8), 0))
        overview_summary.columnconfigure(0, weight=1, uniform="overview_summary")
        overview_summary.columnconfigure(1, weight=1, uniform="overview_summary")
        overview_summary.rowconfigure(0, weight=1)
        gauge_panel = self._panel(overview_summary, "SYSTEM HEALTH", "現在の状態スコア")
        self.gauge_panel = gauge_panel
        gauge_panel.grid(row=0, column=0, sticky="nsew", padx=(0, self._px(8)))
        checks_panel = self._panel(overview_summary, "CHECK MATRIX", "接続・画面・保存")
        self.checks_panel = checks_panel
        checks_panel.grid(row=0, column=1, sticky="nsew", padx=(self._px(8), 0))
        recovery_panel = self._panel(overview, "RECOVERY READINESS", "復元検証と保存容量")
        self.recovery_panel = recovery_panel
        recovery_panel.grid(row=2, column=1, sticky="nsew", padx=(self._px(10), 0), pady=(self._px(8), 0))
        self.map_canvas = self._canvas(map_panel, height=300)
        self.map_canvas.pack(fill="both", expand=True, padx=self._px(14), pady=(0, self._px(14)))
        self.gauge_canvas = self._canvas(gauge_panel, height=128)
        self.gauge_canvas.pack(fill="both", expand=True, padx=self._px(14), pady=(0, self._px(14)))
        self.trend_canvas = self._canvas(trend_panel, height=230)
        self.trend_canvas.pack(fill="both", expand=True, padx=self._px(14), pady=(0, self._px(14)))
        self.health = self._canvas(checks_panel, height=128)
        self.health.pack(fill="both", expand=True, padx=self._px(14), pady=(0, self._px(14)))
        self.recovery_canvas = self._canvas(recovery_panel, height=104)
        self.recovery_canvas.pack(fill="both", expand=True, padx=self._px(14), pady=(0, self._px(14)))
        for canvas in (self.map_canvas, self.gauge_canvas, self.trend_canvas, self.health, self.recovery_canvas):
            canvas.bind("<Configure>", lambda _event: self._redraw_visuals())
        trends_controls = ttk.Frame(trends, style="Surface.TFrame")
        self.trends_controls = trends_controls
        trends_controls.pack(fill="x", pady=(0, self._px(8)))
        trends_filter_group = ttk.Frame(trends_controls, style="Surface.TFrame")
        self.trends_filter_group = trends_filter_group
        trends_filter_group.pack(side="left")
        ttk.Label(trends_filter_group, text="表示期間", style="Section.TLabel").pack(side="left")
        trend_window = ttk.Combobox(
            trends_filter_group,
            textvariable=self.trends_window_filter,
            values=TIME_WINDOW_OPTIONS[:3],
            state="readonly",
            width=11,
        )
        trend_window.pack(side="left", padx=(self._px(8), self._px(6)))
        trend_window.bind("<<ComboboxSelected>>", lambda _event: self.refresh_trends())
        ttk.Button(trends_filter_group, text="更新", command=self.refresh_trends).pack(side="left")
        self.trends_summary = tk.StringVar(value="永続ヘルス履歴を読み込み中")
        self.trends_summary_label = ttk.Label(trends_controls, textvariable=self.trends_summary, style="FilterMeta.TLabel")
        self.trends_summary_label.pack(side="right")
        status_history_panel = self._panel(trends, "HEALTH HISTORY", "L1〜L3の5分集計・欠損も表示")
        status_history_panel.pack(fill="x", pady=(0, self._px(8)))
        self.status_history_canvas = self._canvas(status_history_panel, height=220)
        self.status_history_canvas.pack(fill="x", padx=self._px(14), pady=(0, self._px(14)))
        task_trend_panel = self._panel(trends, "JOB FRESHNESS", "タスクと復元検証の最終成功")
        self.task_trend_panel = task_trend_panel
        task_trend_panel.pack(fill="x", pady=(0, self._px(8)))
        self.task_trend_canvas = self._canvas(task_trend_panel, height=156)
        self.task_trend_canvas.pack(fill="both", expand=True, padx=self._px(14), pady=(0, self._px(14)))
        trends_lower = ttk.Frame(trends, style="Surface.TFrame")
        self.trends_lower = trends_lower
        trends_lower.pack(fill="both", expand=True)
        trends_lower.columnconfigure(0, weight=1, uniform="trend_lower")
        trends_lower.columnconfigure(1, weight=1, uniform="trend_lower")
        latency_panel = self._panel(trends_lower, "RESPONSE LATENCY", "Streamlit応答の5分 p95")
        self.latency_panel = latency_panel
        latency_panel.grid(row=0, column=0, sticky="nsew", padx=(0, self._px(4)))
        capacity_panel = self._panel(trends_lower, "STORAGE HEADROOM", "SMAIデータとRuntimeの空き容量")
        self.capacity_panel = capacity_panel
        capacity_panel.grid(row=0, column=1, sticky="nsew", padx=(self._px(4), 0))
        self.latency_canvas = self._canvas(latency_panel, height=170)
        self.latency_canvas.pack(fill="both", expand=True, padx=self._px(14), pady=(0, self._px(14)))
        self.capacity_canvas = self._canvas(capacity_panel, height=170)
        self.capacity_canvas.pack(fill="both", expand=True, padx=self._px(14), pady=(0, self._px(14)))
        for canvas in (self.status_history_canvas, self.latency_canvas, self.capacity_canvas, self.task_trend_canvas):
            canvas.bind("<Configure>", lambda _event: self._draw_trends())
        sessions_summary = self._panel(sessions, "端末接続状況", "端末種別ごとの現在接続数と監視開始後の累計")
        sessions_summary.pack(fill="x", pady=(0, self._px(8)))
        self.connection_total_summary = tk.StringVar(value="現在接続・累計端末を確認中")
        self.connection_total_summary_label = ttk.Label(
            sessions_summary,
            textvariable=self.connection_total_summary,
            style="CardMeta.TLabel",
            wraplength=self._px(900),
        )
        self.connection_total_summary_label.pack(anchor="w", padx=self._px(14), pady=(0, self._px(6)))
        self.session_canvas = self._canvas(sessions_summary, height=84)
        self.session_canvas.pack(fill="x", padx=12, pady=(0, 12))
        sessions_table = self._panel(sessions, "セッション一覧", "識別子は短縮表示")
        sessions_table.pack(fill="x", pady=(0, self._px(8)))
        self.sessions = self._tree(
            sessions_table,
            (
                ("user", "ユーザー / プロフィール", 210),
                ("client", "端末種別", 130),
                ("heartbeat", "最終通信", 230),
                ("device", "端末擬似ID", 150),
                ("state", "状態", 150),
            ),
        )
        connection_history_panel = self._panel(
            sessions,
            "接続観測履歴",
            "Analyticsが観測した状態変化。消失は切断と推測しません",
        )
        connection_history_panel.pack(fill="x")
        self.connection_history = self._tree(
            connection_history_panel,
            (
                ("time", "観測時刻", 190),
                ("client", "端末種別", 140),
                ("event", "観測結果", 210),
                ("status", "状態", 130),
                ("session", "セッション", 180),
            ),
        )
        activity_summary = self._panel(history, "操作サマリー", "直近の操作と結果")
        activity_summary.pack(fill="x", pady=(0, self._px(8)))
        self.activity_canvas = self._canvas(activity_summary, height=84)
        self.activity_canvas.pack(fill="x", padx=12, pady=(0, 12))
        controls = ttk.Frame(history, style="Surface.TFrame")
        controls.pack(fill="x", pady=(0, self._px(8)))
        self.history_controls = controls
        history_period = ttk.Frame(controls, style="Surface.TFrame")
        ttk.Label(history_period, text="期間", style="Section.TLabel").pack(side="left")
        self.history_window_filter = tk.StringVar(value="過去24時間")
        ttk.Combobox(history_period, textvariable=self.history_window_filter, values=TIME_WINDOW_OPTIONS, state="readonly", width=11).pack(side="left", padx=(self._px(8), 0))
        history_result = ttk.Frame(controls, style="Surface.TFrame")
        ttk.Label(history_result, text="結果", style="Section.TLabel").pack(side="left")
        self.history_filter = tk.StringVar(value="すべて")
        ttk.Combobox(history_result, textvariable=self.history_filter, values=HISTORY_RESULT_OPTIONS, state="readonly", width=10).pack(side="left", padx=(self._px(8), 0))
        history_user = ttk.Frame(controls, style="Surface.TFrame")
        ttk.Label(history_user, text="ユーザーID", style="Section.TLabel").pack(side="left")
        self.history_user_filter = tk.StringVar()
        ttk.Entry(history_user, textvariable=self.history_user_filter, width=16).pack(side="left", fill="x", expand=True, padx=(self._px(6), 0))
        history_action = ttk.Frame(controls, style="Surface.TFrame")
        ttk.Label(history_action, text="操作名", style="Section.TLabel").pack(side="left")
        self.history_action_filter = tk.StringVar()
        ttk.Entry(history_action, textvariable=self.history_action_filter, width=18).pack(side="left", fill="x", expand=True, padx=(self._px(6), 0))
        history_actions = ttk.Frame(controls, style="Surface.TFrame")
        ttk.Button(history_actions, text="絞り込む", command=self.refresh_history).pack(side="left", padx=(0, self._px(4)))
        ttk.Button(history_actions, text="リセット", command=self._clear_history_filters).pack(side="left")
        self.history_result_summary = tk.StringVar(value="表示件数: —")
        history_summary = ttk.Frame(controls, style="Surface.TFrame")
        ttk.Label(history_summary, textvariable=self.history_result_summary, style="FilterMeta.TLabel").pack(anchor="w")
        self.history_control_groups = (history_period, history_result, history_user, history_action, history_actions, history_summary)
        self.history = self._tree(history, (("time", "時刻", 180), ("user", "ユーザー", 140), ("action", "操作", 190), ("target", "対象", 220), ("result", "結果", 110), ("device", "端末", 130), ("duration", "所要時間", 100)))
        incident_summary = self._panel(incidents, "障害状況", "失敗した操作と確認状況")
        incident_summary.pack(fill="x", pady=(0, self._px(8)))
        self.incident_canvas = self._canvas(incident_summary, height=84)
        self.incident_canvas.pack(fill="x", padx=12, pady=(0, 12))
        incident_controls = ttk.Frame(incidents, style="Surface.TFrame")
        incident_controls.pack(fill="x", pady=(0, self._px(8)))
        self.incident_controls = incident_controls
        incident_period = ttk.Frame(incident_controls, style="Surface.TFrame")
        ttk.Label(incident_period, text="期間", style="Section.TLabel").pack(side="left")
        self.incident_window_filter = tk.StringVar(value="過去7日間")
        ttk.Combobox(incident_period, textvariable=self.incident_window_filter, values=TIME_WINDOW_OPTIONS, state="readonly", width=11).pack(side="left", padx=(self._px(8), 0))
        incident_result = ttk.Frame(incident_controls, style="Surface.TFrame")
        ttk.Label(incident_result, text="重要度", style="Section.TLabel").pack(side="left")
        self.incident_filter = tk.StringVar(value="すべて")
        ttk.Combobox(incident_result, textvariable=self.incident_filter, values=INCIDENT_SEVERITY_OPTIONS, state="readonly", width=10).pack(side="left", padx=(self._px(8), 0))
        incident_actions = ttk.Frame(incident_controls, style="Surface.TFrame")
        ttk.Button(incident_actions, text="絞り込む", command=self.refresh_incidents).pack(side="left", padx=(0, self._px(4)))
        ttk.Button(incident_actions, text="リセット", command=self._clear_incident_filters).pack(side="left")
        self.incident_result_summary = tk.StringVar(value="表示件数: —")
        incident_summary_label = ttk.Frame(incident_controls, style="Surface.TFrame")
        ttk.Label(incident_summary_label, textvariable=self.incident_result_summary, style="FilterMeta.TLabel").pack(anchor="w")
        self.incident_control_groups = (incident_period, incident_result, incident_actions, incident_summary_label)
        incident_table = self._panel(incidents, "障害一覧", "失敗・エラー・重大な操作")
        incident_table.pack(fill="both", expand=True)
        self.incidents = self._tree(incident_table, (("time", "時刻", 190), ("action", "操作", 210), ("target", "対象", 280), ("result", "結果", 130)))
        report_summary = self._panel(
            reports,
            "改善レポート",
            "重大な障害の調査結果",
        )
        report_summary.pack(fill="x", pady=(0, self._px(8)))
        self.report_summary_label = ttk.Label(
            report_summary,
            text="重大な障害の調査結果を表示します。通知メールは設定済みの場合のみ送信されます。",
            style="CardMeta.TLabel",
            wraplength=self._px(950),
        )
        self.report_summary_label.pack(anchor="w", padx=self._px(14), pady=(0, self._px(12)))
        report_table = self._panel(reports, "レポート一覧", "最新100件")
        report_table.pack(fill="both", expand=True)
        self.reports = self._tree(
            report_table,
            (
                ("time", "記録時刻", 190),
                ("request", "調査依頼", 290),
                ("severity", "重要度", 120),
                ("status", "状態", 180),
                ("summary", "改善結果", 460),
            ),
        )
        task_summary = self._panel(tasks, "タスク鮮度", "Schedulerと復元検証の最終成功を確認")
        task_summary.pack(fill="x", pady=(0, self._px(8)))
        self.task_canvas = self._canvas(task_summary, height=84)
        self.task_canvas.pack(fill="x", padx=12, pady=(0, 12))
        task_table = self._panel(tasks, "タスク一覧", "最終実行・次回予定・結果を確認")
        task_table.pack(fill="both", expand=True)
        self.tasks = self._tree(
            task_table,
            (
                ("task", "タスク", 260),
                ("status", "鮮度", 130),
                ("last", "最終実行", 190),
                ("next", "次回予定", 170),
                ("result", "最終結果", 120),
                ("detail", "判定理由", 330),
            ),
        )
        log_summary = self._panel(logs, "ログ概要", "直近100行の集計")
        log_summary.pack(fill="x", pady=(0, self._px(8)))
        self.log_canvas = self._canvas(log_summary, height=84)
        self.log_canvas.pack(fill="x", padx=12, pady=(0, 12))
        log_detail = self._panel(logs, "ログ一覧", "最新100行")
        log_detail.pack(fill="both", expand=True)
        log_body = ttk.Frame(log_detail, style="Card.TFrame")
        self.log_body = log_body
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
        self._summary_canvases = (self.session_canvas, self.activity_canvas, self.incident_canvas, self.task_canvas, self.log_canvas)
        for canvas in self._summary_canvases:
            canvas.bind("<Configure>", lambda _event: self._draw_tab_visuals())
        footer = ttk.Frame(outer, style="App.TFrame")
        footer.pack(fill="x", pady=(self._px(8), 0))
        self.footer_context_label = ttk.Label(footer, text=f"Project  {PROJECT_ROOT.name}    Runtime  {RUNTIME_ROOT.name}", style="Subtitle.TLabel")
        self.footer_context_label.pack(side="left")
        self.footer_refresh_label = ttk.Label(footer, textvariable=self.refresh_state, style="Subtitle.TLabel")
        self.footer_refresh_label.pack(side="right")

    def _panel(self, parent: ttk.Frame, title: str, subtitle: str) -> ttk.Frame:
        panel = ttk.Frame(parent, style="Card.TFrame", padding=(self._px(14), self._px(12)))
        header = ttk.Frame(panel, style="Card.TFrame")
        header.pack(fill="x", pady=(0, self._px(10)))
        ttk.Label(header, text=title, style="CardLabel.TLabel").pack(side="left")
        subtitle_label = ttk.Label(header, text=subtitle, style="CardMeta.TLabel")
        subtitle_label.pack(side="right")
        self.panel_subtitles.append(subtitle_label)
        return panel

    def _canvas(self, parent: ttk.Frame, *, height: int) -> tk.Canvas:
        return tk.Canvas(parent, height=self._px(height), bg=COLORS["card"], highlightthickness=0, bd=0)

    def _tree(self, parent: ttk.Frame, columns: tuple[tuple[str, str, int], ...]) -> ttk.Treeview:
        body = ttk.Frame(parent, style="Card.TFrame")
        if not hasattr(self, "tree_bodies"):
            self.tree_bodies: list[ttk.Frame] = []
        self.tree_bodies.append(body)
        body.pack(fill="both", expand=True)
        tree = ttk.Treeview(body, columns=tuple(item[0] for item in columns), show="headings", height=12)
        if not hasattr(self, "operation_trees"):
            self.operation_trees: list[ttk.Treeview] = []
        self.operation_trees.append(tree)
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
        if normalized in {"degraded", "stale", "cancelled", "disabled", "queued", "path mismatch"}:
            return "degraded"
        if normalized in {"ok", "healthy", "active", "running", "ready", "path verified"}:
            return "healthy"
        return "unknown"

    def _redraw_visuals(self) -> None:
        if not hasattr(self, "map_canvas"):
            return
        self._draw_service_map()
        self._draw_gauge()
        self._draw_trend()
        self._draw_recovery()
        self._draw_trends()

    def _animate_topology(self) -> None:
        self.flow_phase = (self.flow_phase + 1) % 24
        if hasattr(self, "map_canvas"):
            self._draw_service_map()
        self.root.after(420, self._animate_topology)

    def _health_narrative(self) -> tuple[str, str, str]:
        overall = self.status.get().lower()
        checked = self.checked.get()
        if overall == "healthy":
            return ("運用は安定", "接続・画面応答・ローカル保存の3観点が、直近チェックで正常です。", f"最終チェック {checked}。通常監視を継続します。")
        if overall == "degraded":
            return ("一部の観測点に注意", "入口は到達可能ですが、画面応答またはローカル保存に確認が必要な項目があります。", "CHECK MATRIX の黄色行から、影響範囲と確認先を確認してください。")
        if overall == "critical":
            return ("サービス継続性に影響", "入口への接続確認に失敗があります。利用者影響が発生し得るため優先調査が必要です。", "接続経路とStreamlitプロセスを最優先で確認してください。")
        return ("監視証跡を取得できません", "現在の状態を正常と判断できるスナップショットがありません。", "health.py とRuntimeへの書き込み状態を確認してください。")

    def _draw_service_map(self) -> None:
        canvas = self.map_canvas
        canvas.delete("all")
        width = max(canvas.winfo_width(), 400)
        height = max(canvas.winfo_height(), 180)
        compact = self.compact_layout or height < self._px(230)
        # The three client categories make device coverage explicit.  Their
        # connection state is based on the last received heartbeat, never on
        # an assumption that an unobserved device is healthy.
        if compact:
            nodes = [
                ("SMAI UI", "PC ブラウザ", 0.16, 0.24),
                ("スマートフォン", "スマートフォン", 0.50, 0.16),
                ("タブレット", "タブレット", 0.84, 0.24),
                ("Streamlit", "Web App", 0.50, 0.51),
                ("Runtime", "Local Server", 0.76, 0.77),
                ("Analytics", "Ops Console", 0.23, 0.77),
            ]
        elif width < height * 1.25:
            nodes = [
                ("SMAI UI", "PC ブラウザ", 0.16, 0.20),
                ("スマートフォン", "スマートフォン", 0.50, 0.20),
                ("タブレット", "タブレット", 0.84, 0.20),
                ("Streamlit", "Web App", 0.50, 0.53),
                ("Runtime", "Local Server", 0.74, 0.79),
                ("Analytics", "Ops Console", 0.26, 0.79),
            ]
        else:
            nodes = [
                ("SMAI UI", "PC ブラウザ", 0.13, 0.20),
                ("スマートフォン", "スマートフォン", 0.50, 0.20),
                ("タブレット", "タブレット", 0.87, 0.20),
                ("Streamlit", "Web App", 0.50, 0.53),
                ("Runtime", "Local Server", 0.78, 0.79),
                ("Analytics", "Ops Console", 0.22, 0.79),
            ]
        points = {}
        for label, _, x, y in nodes:
            points[label] = (width * x, height * y)
        statuses = {
            "SMAI UI": self._client_status("desktop"),
            "スマートフォン": self._client_status("smartphone"),
            "タブレット": self._client_status("tablet"),
            "Streamlit": self._service_status("streamlit"),
            "Runtime": self._service_status("server ops", "runtime"),
            "Analytics": self.status.get().lower(),
        }
        edges = (
            ("SMAI UI", "Streamlit"),
            ("スマートフォン", "Streamlit"),
            ("タブレット", "Streamlit"),
            ("Streamlit", "Runtime"),
            ("Streamlit", "Analytics"),
        )
        for index, (left, right) in enumerate(edges):
            x1, y1 = points[left]
            x2, y2 = points[right]
            edge = self._worst_status(statuses[left], statuses[right])
            color = self._status_color(edge)
            connected = edge in {"ok", "healthy", "active", "running"}
            canvas.create_line(x1, y1, x2, y2, fill=color if connected else COLORS["border_strong"], width=self._px(3), dash=() if connected else (self._px(5), self._px(4)))
            if connected:
                progress = ((self.flow_phase + index * 5) % 24) / 24
                px, py = x1 + (x2 - x1) * progress, y1 + (y2 - y1) * progress
                dot = self._px(5)
                canvas.create_oval(px - dot, py - dot, px + dot, py + dot, fill=COLORS["cyan"], outline="")
        for label, device, _, _ in nodes:
            x, y = points[label]
            color = self._status_color(statuses[label])
            radius = self._px(23 if compact else 33)
            canvas.create_oval(x - radius, y - radius, x + radius, y + radius, fill=COLORS["elevated"], outline=color, width=self._px(2))
            icon = self.topology_images.get(label)
            if icon is not None:
                canvas.create_image(x, y, image=icon)
            elif label == "スマートフォン":
                self._draw_client_device(canvas, x, y, color, phone=True, compact=compact)
            elif label == "タブレット":
                self._draw_client_device(canvas, x, y, color, phone=False, compact=compact)
            else:
                canvas.create_text(x, y, text=device, fill=color, font=self._font(9, "bold"))
            if compact:
                canvas.create_text(
                    x,
                    min(y + radius + self._px(10), height - self._px(8)),
                    text=label,
                    fill=color,
                    font=self._font(7, "bold"),
                )
            else:
                canvas.create_text(x, min(y + self._px(45), height - self._px(20)), text=label, fill=COLORS["heading"], font=self._font(10, "bold"))
                canvas.create_text(x, min(y + self._px(61), height - self._px(6)), text=f"{device} · {statuses[label].upper()}", fill=color, font=self._font(8))
        canvas.create_text(
            self._px(16),
            self._px(14),
            text="端末からの接続経路" if compact else "端末からの接続経路 · 水色の点は90秒以内の通信確認",
            anchor="nw",
            fill=COLORS["muted"],
            font=self._font(8 if compact else 9, "bold"),
        )
        if not compact:
            canvas.create_text(width - self._px(12), height - self._px(10), text="点線=通信証跡なし  /  黄色・赤=要確認", anchor="se", fill=COLORS["muted"], font=self._font(9))

    def _draw_client_device(self, canvas: tk.Canvas, x: float, y: float, color: str, *, phone: bool, compact: bool) -> None:
        """Draw code-native phone/tablet icons so the topology needs no tracking asset."""

        scale = self._px(0.70 if compact else 1.0)
        half_width = scale * (7 if phone else 15)
        half_height = scale * (15 if phone else 10)
        canvas.create_rectangle(x - half_width, y - half_height, x + half_width, y + half_height, fill=COLORS["page"], outline=color, width=self._px(2))
        inset = self._px(3)
        canvas.create_rectangle(x - half_width + inset, y - half_height + inset, x + half_width - inset, y + half_height - inset, fill=COLORS["surface"], outline=COLORS["blue"])
        if phone:
            canvas.create_oval(x - self._px(1), y + half_height - self._px(4), x + self._px(1), y + half_height - self._px(2), fill=color, outline="")
        else:
            canvas.create_oval(x + half_width - self._px(4), y - self._px(1), x + half_width - self._px(2), y + self._px(1), fill=color, outline="")

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

    @staticmethod
    def _worst_status(*statuses: str) -> str:
        return worst_status(*statuses)

    def _draw_gauge(self) -> None:
        canvas = self.gauge_canvas
        canvas.delete("all")
        width = max(canvas.winfo_width(), 260)
        height = max(canvas.winfo_height(), 180)
        score = self._health_score(self.status.get().lower())
        color = self._status_color(self.status.get().lower())
        title, summary, action = self._health_narrative()
        size = min(self._px(145), max(self._px(108), min(width * 0.32, height - self._px(38))))
        cx, cy = width * 0.23, height / 2 + self._px(5)
        box = (cx - size / 2, cy - size / 2, cx + size / 2, cy + size / 2)
        canvas.create_arc(*box, start=135, extent=-270, style="arc", outline=COLORS["elevated"], width=self._px(13))
        canvas.create_arc(*box, start=135, extent=-270 * score / 100, style="arc", outline=color, width=self._px(13))
        canvas.create_text(cx, cy - self._px(4), text=str(score), fill=COLORS["heading"], font=self._font(24, "bold"))
        canvas.create_text(cx, cy + self._px(25), text="/ 100", fill=COLORS["muted"], font=self._font(9))
        canvas.create_text(cx, self._px(15), text=self.status.get(), fill=color, font=self._font(10, "bold"))
        text_x = width * 0.43
        canvas.create_text(text_x, self._px(28), text=title, anchor="nw", fill=color, font=self._font(12, "bold"))
        canvas.create_text(text_x, self._px(54), text=summary, anchor="nw", width=width - text_x - self._px(16), fill=COLORS["text"], font=self._font(9), justify="left")
        canvas.create_text(text_x, height - self._px(42), text=action, anchor="nw", width=width - text_x - self._px(16), fill=COLORS["muted"], font=self._font(8), justify="left")
        canvas.create_text(text_x, height - self._px(18), text="SCORE: 接続 / 画面 / 保存", anchor="nw", fill=COLORS["blue"], font=self._font(8, "bold"))

    def _draw_trend(self) -> None:
        canvas = self.trend_canvas
        canvas.delete("all")
        width = max(canvas.winfo_width(), 400)
        height = max(canvas.winfo_height(), 120)
        left, right, top, bottom = self._px(38), width - self._px(18), self._px(48), height - self._px(40)
        zones = ((80, 100, "#123C39", "NORMAL ≥80"), (50, 80, "#3C3518", "WATCH 50–79"), (0, 50, "#40222A", "CRITICAL <50"))
        for low, high, fill, label in zones:
            y1 = bottom - (bottom - top) * high / 100
            y2 = bottom - (bottom - top) * low / 100
            canvas.create_rectangle(left, y1, right, y2, fill=fill, outline="")
            canvas.create_text(right - self._px(4), (y1 + y2) / 2, text=label, anchor="e", fill=COLORS["muted"], font=self._font(7, "bold"))
        for ratio in (0.0, 0.5, 0.8, 1.0):
            y = bottom - (bottom - top) * ratio
            canvas.create_line(left, y, right, y, fill=COLORS["border"], dash=(2, 4))
            canvas.create_text(self._px(4), y, text=str(int(ratio * 100)), anchor="w", fill=COLORS["muted"], font=self._font(8))
        values = [score for _, score in self.health_history[-30:]] or [self._health_score(self.status.get().lower())]
        points = []
        for index, value in enumerate(values):
            x = left if len(values) == 1 else left + (right - left) * index / (len(values) - 1)
            y = bottom - (bottom - top) * value / 100
            points.extend((x, y))
        # Canvas Configure can run before the first refresh has appended a
        # snapshot.  Keep the initial chart drawable instead of indexing an
        # empty timestamp list during a resize.
        times = [timestamp for timestamp, _ in self.health_history[-30:]] or [self.checked.get()]
        time_indexes = [0] if len(times) <= 1 else sorted({0, (len(times) - 1) // 2, len(times) - 1})
        for index in time_indexes:
            x = left if len(times) == 1 else left + (right - left) * index / (len(times) - 1)
            canvas.create_line(x, top, x, bottom, fill=COLORS["border"], dash=(2, 4))
            canvas.create_text(x, bottom + self._px(16), text=compact_timestamp(times[index]), fill=COLORS["muted"], font=self._font(8))
        if len(points) >= 4:
            for index in range(len(values) - 1):
                segment_score = values[index + 1]
                start = index * 2
                canvas.create_line(*points[start:start + 4], fill=self._status_color("healthy" if segment_score >= 80 else "degraded" if segment_score >= 50 else "critical"), width=self._px(3), smooth=True)
        for index in range(0, len(points), 2):
            radius = self._px(3)
            point_color = self._status_color("healthy" if values[index // 2] >= 80 else "degraded" if values[index // 2] >= 50 else "critical")
            canvas.create_oval(points[index] - radius, points[index + 1] - radius, points[index] + radius, points[index + 1] + radius, fill=point_color, outline=COLORS["card"])
        message = "安定" if all(value >= 80 for value in values) else "注意: 閾値を下回った履歴あり"
        canvas.create_text(left, self._px(4), text=f"総合スコア · {message}", anchor="nw", fill=COLORS["heading"], font=self._font(9, "bold"))
        canvas.create_text(right, self._px(22), text="緑: 正常  /  黄: 注意  /  赤: 早期対応", anchor="ne", fill=COLORS["muted"], font=self._font(8))

    def _draw_recovery(self) -> None:
        if not hasattr(self, "recovery_canvas"):
            return
        canvas = self.recovery_canvas
        smoke_status = str(self.backup_smoke.get("overall") or "unknown").lower()
        checked_at = self.backup_smoke.get("checked_at")
        restore_value = "未記録" if smoke_status == "unknown" else smoke_status.upper()
        restore_detail = "復元スモークの記録がありません" if smoke_status == "unknown" else f"最終検証 {relative_time(checked_at)}"
        storage_rows = [item for item in self.latest_storage if isinstance(item, dict)]
        available_storage = [item for item in storage_rows if isinstance(item.get("free_percent"), (int, float))]
        if available_storage:
            lowest = min(available_storage, key=lambda item: float(item.get("free_percent", 0)))
            headroom_value = f"{float(lowest['free_percent']):.1f}%"
            headroom_detail = f"最小空き容量 · {lowest.get('name', 'volume')}"
            headroom_color = COLORS["red"] if float(lowest["free_percent"]) < 5 else COLORS["amber"] if float(lowest["free_percent"]) < 15 else COLORS["green"]
        else:
            headroom_value, headroom_detail, headroom_color = "—", "容量の観測記録がありません", COLORS["muted"]
        coverage = telemetry.window_summary(self.health_rollups, window=telemetry_window(self.trends_window_filter.get()))
        coverage_value = f"{coverage['coverage_percent']}%"
        coverage_detail = f"履歴観測 {coverage['available_buckets']} / {coverage['expected_buckets']} 枠"
        coverage_color = COLORS["green"] if float(coverage["coverage_percent"]) >= 95 else COLORS["amber"] if float(coverage["coverage_percent"]) else COLORS["muted"]
        self._draw_summary_metrics(
            canvas,
            (
                ("復元検証", restore_value, restore_detail, self._status_color(smoke_status)),
                ("保存容量", headroom_value, headroom_detail, headroom_color),
                ("履歴カバレッジ", coverage_value, coverage_detail, coverage_color),
            ),
        )

    def refresh_trends(self) -> None:
        """Refresh durable telemetry without treating missing records as healthy."""

        window = telemetry_window(self.trends_window_filter.get())
        self.health_rollups = telemetry.read_health_rollups(RUNTIME_ROOT, window=window)
        summary = telemetry.window_summary(self.health_rollups, window=window)
        overall = summary.get("overall", {})
        critical = int(overall.get("critical", 0)) if isinstance(overall, dict) else 0
        self.trends_summary.set(
            f"記録 {summary['available_buckets']} / {summary['expected_buckets']} 枠 · "
            f"カバレッジ {summary['coverage_percent']}% · Critical {critical}"
        )
        latest = self.health_rollups[-1] if self.health_rollups else {}
        storage = latest.get("storage") if isinstance(latest, dict) else None
        if isinstance(storage, list):
            self.latest_storage = [item for item in storage if isinstance(item, dict)]
        if not self.latest_storage:
            snapshot = read_json(SNAPSHOT)
            snapshot_storage = snapshot.get("storage")
            self.latest_storage = [item for item in snapshot_storage if isinstance(item, dict)] if isinstance(snapshot_storage, list) else []
        self.backup_smoke = read_json(BACKUP_SMOKE_STATE)
        self.task_observations = task_monitor.read_observations(RUNTIME_ROOT, window=window)
        self._draw_recovery()
        self._draw_trends()

    def _trend_range(self) -> tuple[datetime, datetime, timedelta]:
        window = telemetry_window(self.trends_window_filter.get())
        current = datetime.now(UTC)
        return current - window, current, window

    def _draw_trends(self) -> None:
        if not hasattr(self, "status_history_canvas"):
            return
        self._draw_status_history()
        self._draw_latency_history()
        self._draw_capacity_history()
        self._draw_task_history()

    def _draw_status_history(self) -> None:
        canvas = self.status_history_canvas
        canvas.delete("all")
        width = max(canvas.winfo_width(), 480)
        height = max(canvas.winfo_height(), self._px(180))
        start, end, window = self._trend_range()
        left, right = self._px(68), width - self._px(12)
        top, bottom = self._px(38), height - self._px(26)
        row_height = max(self._px(22), (bottom - top) / 3)
        levels = ("L1", "L2", "L3")
        labels = {"L1": "L1 接続", "L2": "L2 画面", "L3": "L3 保存"}
        for index, level in enumerate(levels):
            y1 = top + row_height * index + self._px(2)
            y2 = top + row_height * (index + 1) - self._px(2)
            canvas.create_rectangle(left, y1, right, y2, fill=COLORS["elevated"], outline="")
            canvas.create_text(self._px(4), (y1 + y2) / 2, text=labels[level], anchor="w", fill=COLORS["muted"], font=self._font(8, "bold"))
        seconds = max(1.0, window.total_seconds())
        for row in self.health_rollups:
            observed = parse_timestamp(row.get("bucket_start"))
            if observed is None or not start <= observed <= end:
                continue
            x = left + (observed - start).total_seconds() / seconds * (right - left)
            bucket_width = max(1.0, telemetry.BUCKET_SECONDS / seconds * (right - left))
            for index, level in enumerate(levels):
                status = telemetry.level_status(row, level)
                y1 = top + row_height * index + self._px(2)
                y2 = top + row_height * (index + 1) - self._px(2)
                canvas.create_rectangle(x, y1, min(right, x + bucket_width + 0.5), y2, fill=self._status_color(status), outline="")
        summary = telemetry.window_summary(self.health_rollups, window=window)
        canvas.create_text(
            left,
            self._px(5),
            text=f"5分枠の最悪状態 · 記録カバレッジ {summary['coverage_percent']}%（灰=欠損/不明）",
            anchor="nw",
            fill=COLORS["heading"],
            font=self._font(9, "bold"),
        )
        for ratio, label in ((0, start.strftime("%m/%d %H:%M")), (0.5, (start + window / 2).strftime("%m/%d %H:%M")), (1, end.strftime("%m/%d %H:%M"))):
            x = left + ratio * (right - left)
            canvas.create_line(x, top, x, bottom, fill=COLORS["border"], dash=(2, 4))
            canvas.create_text(x, height - self._px(7), text=label, anchor="s", fill=COLORS["muted"], font=self._font(8))
        if not self.health_rollups:
            canvas.create_text(left, (top + bottom) / 2, text="永続ヘルス履歴はまだありません。最初の5分集計後に表示します。", anchor="w", fill=COLORS["muted"], font=self._font(9))

    def _trend_points(self, series: list[tuple[datetime, float]], *, left: float, right: float, top: float, bottom: float, start: datetime, end: datetime, maximum: float) -> list[float]:
        if not series or maximum <= 0:
            return []
        seconds = max(1.0, (end - start).total_seconds())
        points: list[float] = []
        for observed, value in series:
            if not start <= observed <= end:
                continue
            x = left + (observed - start).total_seconds() / seconds * (right - left)
            y = bottom - min(1.0, max(0.0, value / maximum)) * (bottom - top)
            points.extend((x, y))
        return points

    def _draw_latency_history(self) -> None:
        canvas = self.latency_canvas
        canvas.delete("all")
        width, height = max(canvas.winfo_width(), 300), max(canvas.winfo_height(), self._px(140))
        start, end, _window = self._trend_range()
        left, right, top, bottom = self._px(30), width - self._px(10), self._px(24), height - self._px(24)
        series_by_name: dict[str, list[tuple[datetime, float]]] = {"Streamlit health": [], "Streamlit page": []}
        for row in self.health_rollups:
            observed = parse_timestamp(row.get("bucket_start"))
            latency = row.get("latency_ms")
            if observed is None or not isinstance(latency, dict):
                continue
            for name in series_by_name:
                metric = latency.get(name)
                if isinstance(metric, dict) and isinstance(metric.get("p95_ms"), int):
                    series_by_name[name].append((observed, float(metric["p95_ms"])))
        values = [value for series in series_by_name.values() for _time, value in series]
        if not values:
            canvas.create_text(self._px(8), self._px(12), text="応答時間の履歴はまだありません。", anchor="nw", fill=COLORS["muted"], font=self._font(9))
            return
        maximum = max(100.0, max(values) * 1.15)
        for ratio in (0, 0.5, 1):
            y = bottom - ratio * (bottom - top)
            canvas.create_line(left, y, right, y, fill=COLORS["border"], dash=(2, 4))
            canvas.create_text(self._px(3), y, text=f"{int(maximum * ratio)}", anchor="w", fill=COLORS["muted"], font=self._font(7))
        colors = {"Streamlit health": COLORS["cyan"], "Streamlit page": COLORS["blue"]}
        for index, (name, series) in enumerate(series_by_name.items()):
            points = self._trend_points(series, left=left, right=right, top=top, bottom=bottom, start=start, end=end, maximum=maximum)
            if len(points) >= 4:
                canvas.create_line(*points, fill=colors[name], width=self._px(2), smooth=True)
            canvas.create_text(right, self._px(5 + index * 14), text=name, anchor="ne", fill=colors[name], font=self._font(7, "bold"))
        canvas.create_text(left, height - self._px(5), text="ms · 5分 p95", anchor="sw", fill=COLORS["muted"], font=self._font(7))

    def _draw_capacity_history(self) -> None:
        canvas = self.capacity_canvas
        canvas.delete("all")
        width, height = max(canvas.winfo_width(), 300), max(canvas.winfo_height(), self._px(140))
        start, end, _window = self._trend_range()
        left, right, top, bottom = self._px(34), width - self._px(10), self._px(24), height - self._px(24)
        series_by_name: dict[str, list[tuple[datetime, float]]] = {}
        for row in self.health_rollups:
            observed = parse_timestamp(row.get("bucket_start"))
            storage = row.get("storage")
            if observed is None or not isinstance(storage, list):
                continue
            for item in storage:
                if not isinstance(item, dict) or not isinstance(item.get("free_percent"), (int, float)):
                    continue
                name = str(item.get("name") or "Volume")[:24]
                series_by_name.setdefault(name, []).append((observed, float(item["free_percent"])))
        if not series_by_name:
            canvas.create_text(self._px(8), self._px(12), text="保存容量の履歴はまだありません。", anchor="nw", fill=COLORS["muted"], font=self._font(9))
            return
        for percent in (0, 15, 100):
            y = bottom - percent / 100 * (bottom - top)
            color = COLORS["red"] if percent == 15 else COLORS["border"]
            canvas.create_line(left, y, right, y, fill=color, dash=(2, 4))
            canvas.create_text(self._px(3), y, text=f"{percent}%", anchor="w", fill=COLORS["muted"], font=self._font(7))
        colors = (COLORS["green"], COLORS["cyan"], COLORS["blue"])
        for index, (name, series) in enumerate(sorted(series_by_name.items())[:3]):
            points = self._trend_points(series, left=left, right=right, top=top, bottom=bottom, start=start, end=end, maximum=100)
            color = colors[index]
            if len(points) >= 4:
                canvas.create_line(*points, fill=color, width=self._px(2), smooth=True)
            latest = series[-1][1]
            canvas.create_text(right, self._px(5 + index * 14), text=f"{name} {latest:.1f}%", anchor="ne", fill=color, font=self._font(7, "bold"))
        canvas.create_text(left, height - self._px(5), text="空き容量 · 赤線=15%注意", anchor="sw", fill=COLORS["muted"], font=self._font(7))

    def _draw_task_history(self) -> None:
        canvas = self.task_trend_canvas
        canvas.delete("all")
        width = max(canvas.winfo_width(), 420)
        height = max(canvas.winfo_height(), self._px(130))
        start, end, window = self._trend_range()
        current_names = [str(row.get("name") or "") for row in self.task_rows if row.get("name")]
        historical_names = [
            str(task.get("name") or "")
            for row in self.task_observations
            for task in row.get("tasks", [])
            if isinstance(task, dict) and task.get("name")
        ]
        names = list(dict.fromkeys([*current_names, *historical_names]))[:6]
        if not names:
            canvas.create_text(self._px(8), self._px(12), text="タスク鮮度の履歴はまだありません。", anchor="nw", fill=COLORS["muted"], font=self._font(9))
            return
        left, right = self._px(132), width - self._px(10)
        top, bottom = self._px(28), height - self._px(18)
        row_height = max(self._px(16), (bottom - top) / len(names))
        for index, name in enumerate(names):
            y1 = top + row_height * index + self._px(1)
            y2 = top + row_height * (index + 1) - self._px(1)
            canvas.create_rectangle(left, y1, right, y2, fill=COLORS["elevated"], outline="")
            canvas.create_text(self._px(4), (y1 + y2) / 2, text=name[:20], anchor="w", fill=COLORS["muted"], font=self._font(7, "bold"))
        seconds = max(1.0, window.total_seconds())
        indexed_statuses: dict[tuple[int, int], str] = {}
        for observation in self.task_observations:
            observed = parse_timestamp(observation.get("observed_at"))
            tasks = observation.get("tasks")
            if observed is None or not start <= observed <= end or not isinstance(tasks, list):
                continue
            x_index = max(0, min(int(right - left), int((observed - start).total_seconds() / seconds * (right - left))))
            status_by_name = {
                str(task.get("name") or ""): str(task.get("status") or "unknown")
                for task in tasks
                if isinstance(task, dict)
            }
            for index, name in enumerate(names):
                status = status_by_name.get(name)
                if status:
                    key = (index, x_index)
                    indexed_statuses[key] = worst_status(indexed_statuses.get(key, "healthy"), status)
        for (index, x_index), status in indexed_statuses.items():
            y1 = top + row_height * index + self._px(1)
            y2 = top + row_height * (index + 1) - self._px(1)
            x = left + x_index
            canvas.create_rectangle(x, y1, min(right, x + 1.5), y2, fill=self._status_color(status), outline="")
        canvas.create_text(left, self._px(5), text="5分観測 · 赤=失敗/期限超過  黄=要確認  灰=未観測", anchor="nw", fill=COLORS["heading"], font=self._font(8, "bold"))
        if not self.task_observations:
            canvas.create_text(left, (top + bottom) / 2, text="初回のタスク観測後に、状態変化と実行鮮度を表示します。", anchor="w", fill=COLORS["muted"], font=self._font(8))

    def _draw_checks(self, checks: list[object], overall: str, checked_at: object) -> None:
        canvas = self.health
        canvas.delete("all")
        width = max(canvas.winfo_width(), 300)
        narrow = self.narrow_layout or width < self._px(560)
        title, _, action = self._health_narrative()
        heading = f"{title}  ·  {overall.upper()}" if narrow else f"{title}  ·  {overall.upper()}  ·  {format_timestamp(checked_at)}"
        canvas.create_text(0, self._px(4), text=heading, anchor="nw", width=width - self._px(4), fill=self._status_color(overall), font=self._font(9, "bold"))
        canvas.create_text(0, self._px(20), text="接続=到達性  /  画面=アプリ応答  /  保存=ローカルデータ", anchor="nw", fill=COLORS["muted"], font=self._font(8))
        height = max(canvas.winfo_height(), 90)
        valid_checks = [item for item in checks if isinstance(item, dict)]
        line_height = max(self._px(15), min(self._px(21), (height - self._px(84)) / max(len(valid_checks), 1)))
        y = self._px(48)
        for item in valid_checks:
            status = str(item.get("status", "unknown"))
            dot = self._px(5)
            canvas.create_oval(0, y + self._px(3), dot * 2, y + self._px(3) + dot * 2, fill=self._status_color(status), outline="")
            level = str(item.get("level", "??"))
            category, consequence = {"L1": ("接続確認", "利用者が接続できない可能性"), "L2": ("画面確認", "画面表示・操作に影響"), "L3": ("保存確認", "設定や履歴の保存に影響")}.get(level, ("監視確認", "要確認"))
            status_x = width * (0.72 if narrow else 0.58)
            canvas.create_text(self._px(18), y, text=f"{category}  ·  {item.get('name', 'unknown')}", anchor="nw", width=status_x - self._px(24), fill=COLORS["text"], font=self._font(8))
            if not narrow:
                canvas.create_text(status_x, y, text="正常" if status.lower() in {"ok", "healthy"} else consequence, anchor="nw", width=width * 0.27, fill=self._status_color(status), font=self._font(8, "bold"))
            canvas.create_text(width - self._px(4), y, text="OK" if status.lower() in {"ok", "healthy"} else "要確認", anchor="ne", fill=self._status_color(status), font=self._font(8, "bold"))
            y += line_height
        if not valid_checks:
            canvas.create_text(0, y, text="No readable health checks are available.", anchor="nw", fill=COLORS["muted"], font=self._font(10))
        if height >= self._px(250):
            canvas.create_text(0, height - self._px(26), text="見方: L1 入口到達性（失敗=critical）  /  L2 画面応答  /  L3 ローカル保存（失敗=degraded）", anchor="nw", fill=COLORS["blue"], font=self._font(8, "bold"))
            canvas.create_text(0, height - self._px(10), text=action, anchor="nw", fill=COLORS["muted"], font=self._font(8))

    def _canvas_metric(self, canvas: tk.Canvas, x: float, width: float, label: str, value: str, detail: str, color: str) -> None:
        top = self._px(8)
        bottom = max(top + self._px(64), canvas.winfo_height() - self._px(6))
        card_height = bottom - top
        inset = self._px(16)
        text_width = max(self._px(48), width - inset * 2)
        canvas.create_rectangle(x, top, x + width, bottom, fill=COLORS["surface"], outline=COLORS["border"], width=1)
        canvas.create_rectangle(x, top, x + self._px(4), bottom, fill=color, outline="")
        canvas.create_text(x + inset, top + card_height * 0.20, text=label, anchor="w", width=text_width, fill=COLORS["muted"], font=self._font(9, "bold"))
        canvas.create_text(x + inset, top + card_height * 0.52, text=value, anchor="w", width=text_width, fill=COLORS["heading"], font=self._font(18, "bold"))
        canvas.create_text(x + inset, top + card_height * 0.80, text=detail, anchor="w", width=text_width, fill=COLORS["muted"], font=self._font(8))

    def _draw_summary_metrics(
        self,
        canvas: tk.Canvas,
        metrics: tuple[tuple[str, str, str, str], ...],
    ) -> None:
        """Draw summary values without assuming a three-card-wide canvas."""

        canvas.delete("all")
        width = max(float(canvas.winfo_width()), float(self._px(1)))
        if not metrics:
            return
        # A small page uses compact, stacked rows.  Retaining all three facts
        # is more useful than compressing text into cards that can no longer
        # contain their labels and operational detail.
        if self.micro_layout or width < self._px(470):
            margin = self._px(4)
            available = max(self._px(84), canvas.winfo_height() - margin * (len(metrics) + 1))
            row_height = available / len(metrics)
            inset = self._px(10)
            for index, (label, value, detail, color) in enumerate(metrics):
                top = margin + index * (row_height + margin)
                bottom = top + row_height
                canvas.create_rectangle(0, top, width, bottom, fill=COLORS["surface"], outline=COLORS["border"], width=1)
                canvas.create_rectangle(0, top, self._px(4), bottom, fill=color, outline="")
                canvas.create_text(
                    inset,
                    top + self._px(6),
                    text=label,
                    anchor="nw",
                    width=width * 0.58,
                    fill=COLORS["muted"],
                    font=self._font(8, "bold"),
                )
                canvas.create_text(
                    width - inset,
                    top + self._px(6),
                    text=value,
                    anchor="ne",
                    fill=COLORS["heading"],
                    font=self._font(10, "bold"),
                )
                canvas.create_text(
                    inset,
                    bottom - self._px(5),
                    text=detail,
                    anchor="sw",
                    width=width - inset * 2,
                    fill=COLORS["muted"],
                    font=self._font(7),
                )
            return

        gap = self._px(8)
        card_width = max(self._px(72), (width - gap * (len(metrics) - 1)) / len(metrics))
        for index, (label, value, detail, color) in enumerate(metrics):
            self._canvas_metric(canvas, index * (card_width + gap), card_width, label, value, detail, color)

    def _session_state(self, session: dict[str, str]) -> str:
        return heartbeat_state(session.get("last_seen_at"))

    def _client_status(self, requested_type: str) -> str:
        """Expose per-device communication only when its session evidence is readable."""

        return client_connection_status(
            self.client_sessions,
            requested_type,
            activity_readable=self.activity_readable,
        )

    def _draw_sessions(self) -> None:
        canvas = self.session_canvas
        state = self.connection_watch.get("state")
        watch_ok = bool(self.connection_watch.get("ok")) and isinstance(state, dict)
        counts = connection_watch.summary(state) if watch_ok else {}
        cumulative = counts.get("cumulative", {}) if isinstance(counts, dict) else {}
        metrics: list[tuple[str, str, str, str]] = []
        for index, client_type in enumerate(connection_watch.CLIENT_TYPES):
            label = f"{CLIENT_TYPE_LABELS[client_type]} / 現在接続"
            if not self.activity_readable:
                value, detail, color = "—", "activity state を取得できません", COLORS["muted"]
            elif not watch_ok:
                value = f"{self.current_connection_counts[client_type]}台"
                detail, color = "累計は接続履歴の状態を確認できません", COLORS["amber"]
            else:
                active_count = self.current_connection_counts[client_type]
                cumulative_count = int(cumulative.get(client_type, 0))
                unlinked_count = self.current_unlinked_counts[client_type]
                detail = f"累計 {cumulative_count}台（ID済）"
                if unlinked_count:
                    detail += f" / 未連携 {unlinked_count}"
                value, color = f"{active_count}台", COLORS["green"]
            metrics.append((label, value, detail, color))
        self._draw_summary_metrics(canvas, tuple(metrics))

    def _refresh_connection_total_summary(self) -> None:
        if not self.activity_readable:
            self.connection_total_summary.set("現在接続・累計端末: activity state を取得できないため不明")
            return
        current_total = sum(self.current_connection_counts.values())
        unlinked_total = sum(self.current_unlinked_counts.values())
        state = self.connection_watch.get("state")
        if not bool(self.connection_watch.get("ok")) or not isinstance(state, dict):
            self.connection_total_summary.set(f"現在接続 合計 {current_total}台 / 累計端末は接続履歴の状態を確認できません")
            return
        counts = connection_watch.summary(state)
        total_cumulative = int(counts["total_cumulative"])
        detail = f"現在接続 合計 {current_total}台 / 監視開始後の累計端末 {total_cumulative}台（ID確認済）"
        if unlinked_total:
            detail += f" / 現在 ID未連携 {unlinked_total}件"
        self.connection_total_summary.set(detail)

    def _refresh_connection_history(self) -> None:
        """Render the locally observed connection history without inferring disconnects."""

        if not hasattr(self, "connection_history"):
            return
        for item in self.connection_history.get_children():
            self.connection_history.delete(item)
        if not bool(self.connection_watch.get("ok")):
            self.connection_history.insert(
                "",
                "end",
                values=("—", "—", "接続履歴の状態を読み取れません", str(self.connection_watch.get("reason") or "要確認"), "—"),
                tags=("unknown",),
            )
            return
        if not bool(self.connection_watch.get("available")):
            self.connection_history.insert(
                "",
                "end",
                values=("—", "—", "接続観測はまだ開始されていません", "UNKNOWN", "—"),
                tags=("unknown",),
            )
            return
        state = self.connection_watch.get("state")
        events = state.get("events", []) if isinstance(state, dict) else []
        labels = {
            "observed": "接続を観測",
            "state_changed": "状態変化を観測",
            "observation_lost": "監視対象から消失（切断とは未確定）",
        }
        if not isinstance(events, list) or not events:
            self.connection_history.insert(
                "",
                "end",
                values=("—", "—", "状態変化はまだ記録されていません", "—", "—"),
            )
            return
        for event in reversed(events):
            if not isinstance(event, dict):
                continue
            client_type = str(event.get("client_type") or "unknown")
            status = str(event.get("status") or "unknown")
            self.connection_history.insert(
                "",
                "end",
                values=(
                    format_timestamp(event.get("observed_at")),
                    CLIENT_TYPE_LABELS.get(client_type, CLIENT_TYPE_LABELS["unknown"]),
                    labels.get(str(event.get("event") or ""), "監視結果を確認"),
                    status.upper(),
                    compact_id(event.get("session_id")),
                ),
                tags=(self._tree_status_tag(status),),
            )

    def _draw_activity(self) -> None:
        canvas = self.activity_canvas
        events = self.activity_events
        ok = sum(1 for event in events if str(event.get("result", "")).lower() == "ok")
        failed = sum(1 for event in events if str(event.get("result", "")).lower() in {"failed", "error", "critical"})
        cancelled = sum(1 for event in events if str(event.get("result", "")).lower() == "cancelled")
        self._draw_summary_metrics(
            canvas,
            (
                ("直近イベント", str(len(events)), "最大200件を表示", COLORS["blue"]),
                ("成功", str(ok), "成功した操作", COLORS["green"]),
                ("失敗 / 取消", str(failed + cancelled), f"失敗 {failed} / 取消 {cancelled}", COLORS["red"] if failed else COLORS["amber"]),
            ),
        )

    def _draw_incidents(self) -> None:
        canvas = self.incident_canvas
        count = len(self.incident_events)
        latest = relative_time(self.incident_events[0].get("timestamp")) if self.incident_events else "記録なし"
        critical = sum(1 for event in self.incident_events if str(event.get("result", "")).lower() == "critical")
        self._draw_summary_metrics(
            canvas,
            (
                ("該当件数", str(count), "現在の絞り込み結果", COLORS["red"] if count else COLORS["green"]),
                ("直近の記録", latest, "復旧状況は対象画面で確認", COLORS["amber"] if count else COLORS["green"]),
                ("重大", str(critical), "重大な障害の件数", COLORS["red"] if critical else COLORS["green"]),
            ),
        )

    def _draw_tasks(self) -> None:
        canvas = self.task_canvas
        healthy = sum(1 for row in self.task_rows if row.get("status", "").lower() == "healthy")
        unknown = sum(1 for row in self.task_rows if row.get("status", "").lower() == "unknown")
        attention = len(self.task_rows) - healthy - unknown
        self._draw_summary_metrics(
            canvas,
            (
                ("予定内", str(healthy), "最終成功・パスを確認", COLORS["green"]),
                ("取得不能", str(unknown), "未登録・権限・記録なし", COLORS["amber"] if unknown else COLORS["green"]),
                ("期限超過 / 失敗", str(attention), "復旧または設定を確認", COLORS["red"] if attention else COLORS["green"]),
            ),
        )

    def _draw_logs(self) -> None:
        canvas = self.log_canvas
        errors = sum(any(token in line.lower() for token in ("error", "failed", "critical")) for line in self.log_lines)
        warnings = sum("warn" in line.lower() for line in self.log_lines)
        sources = sum(1 for line in self.log_lines if line.startswith("["))
        self._draw_summary_metrics(
            canvas,
            (
                ("表示行", str(len(self.log_lines)), "直近ログの抜粋", COLORS["blue"]),
                ("警告", str(warnings), "warn を含む行", COLORS["amber"] if warnings else COLORS["green"]),
                ("異常語", str(errors), f"ログソース {sources}件", COLORS["red"] if errors else COLORS["green"]),
            ),
        )

    def _draw_tab_visuals(self) -> None:
        if not hasattr(self, "session_canvas"):
            return
        self._draw_sessions()
        self._draw_activity()
        self._draw_incidents()
        self._draw_tasks()
        self._draw_logs()

    def _set_status(self, overall: str) -> None:
        labels = {"healthy": ("HEALTHY", COLORS["green"], "すべてのチェックが正常"), "degraded": ("DEGRADED", COLORS["amber"], "確認が必要な項目があります"), "critical": ("CRITICAL", COLORS["red"], "重要なチェックが失敗しています"), "unknown": ("UNKNOWN", COLORS["muted"], "状態を確認できません")}
        label, color, detail = labels.get(overall, labels["unknown"])
        self.status.set(label)
        self.status_detail.set(detail)
        self.status_label.configure(fg=color)

    def refresh(self) -> None:
        try:
            subprocess.run([os.environ.get("PYTHON", "python"), str(REPOSITORY_ROOT / "health.py")], timeout=4, check=False, capture_output=True)
        except (OSError, subprocess.TimeoutExpired):
            self.refresh_state.set("ヘルスチェックを起動できないため、直近の状態を表示しています")
        snapshot = read_json(SNAPSHOT)
        overall = str(snapshot.get("overall", "unknown"))
        self._set_status(overall)
        checked_at = snapshot.get("checked_at", "not available")
        self.checked.set(compact_timestamp(checked_at))
        self.checked_summary.set(f"最終確認 {self.checked.get()}")
        checks = snapshot.get("checks", [])
        check_items = checks if isinstance(checks, list) else []
        self.check_statuses = {
            str(item.get("name", "")).lower(): str(item.get("status", "unknown")).lower()
            for item in check_items
            if isinstance(item, dict)
        }
        self.health_history.append((str(checked_at), self._health_score(overall)))
        self.health_history = self.health_history[-30:]
        snapshot_storage = snapshot.get("storage")
        self.latest_storage = [item for item in snapshot_storage if isinstance(item, dict)] if isinstance(snapshot_storage, list) else []
        self._draw_checks(check_items, overall, checked_at)
        activity = read_json(ACTIVITY)
        sessions = activity.get("sessions", {})
        operations = activity.get("operations", {})
        activity_readable = ACTIVITY.is_file() and isinstance(sessions, dict) and isinstance(operations, dict)
        self.activity_readable = activity_readable
        self.session.set(str(len(sessions)) if activity_readable else "—")
        self.operations.set(str(len(operations)) if activity_readable else "—")
        self.session_rows = []
        self.client_sessions = []
        self.current_connection_counts = {client_type: 0 for client_type in connection_watch.CLIENT_TYPES}
        self.current_unlinked_counts = {client_type: 0 for client_type in connection_watch.CLIENT_TYPES}
        for item in self.sessions.get_children():
            self.sessions.delete(item)
        if activity_readable:
            for session_id, raw_session in sessions.items():
                session = session_details(session_id, raw_session)
                heartbeat = session["last_seen_at"]
                communication = session_connection_status(session)
                summary_state = "active" if communication == "ok" else "stale" if communication in {"degraded", "critical"} else "unknown"
                self.session_rows.append((str(session_id), heartbeat, summary_state))
                self.client_sessions.append(session)
                if communication == "ok" and session["client_type"] in self.current_connection_counts:
                    self.current_connection_counts[session["client_type"]] += 1
                    if not session["device_id"]:
                        self.current_unlinked_counts[session["client_type"]] += 1
                state_label = {
                    "ok": "● 接続中",
                    "degraded": "● 要確認",
                    "critical": "● 通信失敗",
                    "unknown": "● 不明",
                }.get(communication, "● 不明")
                user_label = session["profile_name"] or session["user_id"] or compact_id(session_id)
                if session["profile_name"] and session["user_id"]:
                    user_label = f"{session['profile_name']} / {compact_id(session['user_id'])}"
                client_label = CLIENT_TYPE_LABELS[session["client_type"]]
                device_label = compact_id(session["device_id"]) if session["device_id"] else "—"
                if session["connection_state"] not in {"", "connected", "unknown"} and communication != "critical":
                    state_label = f"{state_label} / {session['connection_state']}"
                self.sessions.insert(
                    "",
                    "end",
                    values=(
                        user_label,
                        client_label,
                        f"{relative_time(heartbeat)}  /  {format_timestamp(heartbeat)}",
                        device_label,
                        state_label,
                    ),
                    tags=(self._tree_status_tag(session_connection_status(session)),),
                )
        if not activity_readable:
            self.session_rows.append(("activity-state", None, "unknown"))
            self.sessions.insert("", "end", values=("—", "種別不明", "activity state を読み取れません", "—", "● 不明"), tags=("unknown",))
        elif not self.session_rows:
            self.sessions.insert("", "end", values=("—", "—", "接続中のセッションはありません", "—", "—"))
        if activity_readable:
            observations = [
                {
                    "session_id": session["session_id"],
                    "client_type": session["client_type"],
                    "device_id": session["device_id"],
                    "status": session_connection_status(session),
                }
                for session in self.client_sessions
            ]
            self.connection_watch = connection_watch.observe(observations, CONNECTION_WATCH_STATE)
        else:
            self.connection_watch = connection_watch.read(CONNECTION_WATCH_STATE)
        self._refresh_connection_total_summary()
        self._refresh_connection_history()
        self._redraw_visuals()
        self.activity_events = read_events()
        self.refresh_history()
        self.incident_source_events = [event for event in self.activity_events if str(event.get("result", "")).lower() in {"failed", "error", "critical"}]
        self.refresh_incidents()
        if hasattr(self, "reports"):
            for item in self.reports.get_children():
                self.reports.delete(item)
            report_rows = incident_automation.report_rows()
            for report in report_rows:
                status = str(report.get("status", "unknown"))
                self.reports.insert(
                    "",
                    "end",
                    values=(
                        format_timestamp(report.get("reported_at")),
                        compact_id(report.get("request_id"), limit=28),
                        str(report.get("severity", "" )).upper(),
                        status,
                        str(report.get("summary", "調査結果はまだ記録されていません。")),
                    ),
                    tags=(self._tree_status_tag(status),),
                )
            if not report_rows:
                self.reports.insert(
                    "",
                    "end",
                    values=(
                        "—",
                        "改善レポートはまだありません",
                        "—",
                        "OK",
                        "重大な障害が検知されると、調査結果がここに追加されます。",
                    ),
                )
        self.task_rows = read_task_status()
        for item in self.tasks.get_children():
            self.tasks.delete(item)
        for row in self.task_rows:
            status = str(row.get("status", "unknown"))
            status_label = {
                "healthy": "● 予定内",
                "degraded": "● 要確認",
                "critical": "● 失敗 / 期限超過",
                "unknown": "● 取得不能",
            }.get(status.lower(), f"● {status.upper()}")
            last_run = row.get("last_run_at") or "—"
            next_run = row.get("next_run_at") or "—"
            self.tasks.insert(
                "",
                "end",
                values=(row.get("name", ""), status_label, format_timestamp(last_run), next_run, row.get("last_result") or "—", row.get("detail") or "—"),
                tags=(self._tree_status_tag(status),),
            )
        self.log_lines = recent_logs()
        self.set_text(self.logs, self.log_lines)
        self._draw_tab_visuals()
        self.refresh_trends()
        self.refresh_state.set("5秒ごとに更新  /  最終更新 " + datetime.now().astimezone().strftime("%H:%M:%S"))
        self.root.after(5000, self.refresh)

    def refresh_history(self) -> None:
        if not hasattr(self, "history"):
            return
        selected = result_filter_key(self.history_filter.get())
        window = time_window_key(self.history_window_filter.get())
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
        self.history_result_summary.set(f"表示件数: {matched}")

    def _clear_history_filters(self) -> None:
        self.history_window_filter.set("過去24時間")
        self.history_filter.set("すべて")
        self.history_user_filter.set("")
        self.history_action_filter.set("")
        self.refresh_history()

    def refresh_incidents(self) -> None:
        if not hasattr(self, "incidents"):
            return
        selected = result_filter_key(self.incident_filter.get())
        window = time_window_key(self.incident_window_filter.get())
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
        self.incident_result_summary.set(f"表示件数: {len(self.incident_events)}")

    def _clear_incident_filters(self) -> None:
        self.incident_window_filter.set("過去7日間")
        self.incident_filter.set("すべて")
        self.refresh_incidents()


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
