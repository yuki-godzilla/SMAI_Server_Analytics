"""Read-only SMAI Analytics dashboard for trusted private networks.

This Streamlit surface deliberately owns no SMAI calculation, ranking, or
user-facing application state. It reads stable Operations contracts and runs
the server-local health probe at a bounded interval. The launcher binds it to
a separate port so it never competes with SMAI's primary Streamlit application.
"""

from __future__ import annotations

import html
import json
import os
import subprocess
import sys
from base64 import b64encode
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Mapping

from ..monitoring import connection_watch, task_monitor, telemetry
from ..operations import incident_automation

try:  # Keep pure helper tests usable without the optional Web runtime.
    import streamlit as st
except ImportError:  # pragma: no cover - the web launcher requires Streamlit
    st = None


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = Path(os.environ.get("SMAI_PROJECT_ROOT", r"C:\Users\user\workspace\SMAI_Projects\Smart_Market_AI"))
RUNTIME_ROOT = Path(os.environ.get("SMAI_RUNTIME_ROOT", r"C:\Users\user\workspace\SMAI_Projects\SMAI_Server_Runtime"))
SNAPSHOT = PROJECT_ROOT / "data/ops/server_ops/health_snapshot.json"
ACTIVITY = PROJECT_ROOT / "data/ops/server_ops/activity_state.json"
EVENT_LOG = RUNTIME_ROOT / "audit/events.jsonl"
BACKUP_SMOKE_STATE = RUNTIME_ROOT / "backup_restore_smoke.json"
CONNECTION_WATCH_STATE = RUNTIME_ROOT / "connections/watch_state.json"
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
CLIENT_TYPE_LABELS = {
    "desktop": "PC",
    "smartphone": "スマートフォン",
    "tablet": "タブレット",
    "unknown": "種別不明",
}
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
    "ready": 1,
}
STATUS_LABELS = {
    "healthy": "正常",
    "ok": "正常",
    "active": "接続中",
    "running": "実行中",
    "ready": "準備完了",
    "degraded": "要確認",
    "stale": "期限超過",
    "critical": "重大",
    "failed": "失敗",
    "error": "エラー",
    "unknown": "不明",
}
STATUS_COLORS = {
    "healthy": "#34D399",
    "ok": "#34D399",
    "active": "#34D399",
    "running": "#34D399",
    "ready": "#34D399",
    "degraded": "#FBBF24",
    "stale": "#FBBF24",
    "critical": "#F87171",
    "failed": "#F87171",
    "error": "#F87171",
    "unknown": "#AAB8C8",
}
TIME_WINDOW_OPTIONS = {
    "過去24時間": timedelta(hours=24),
    "過去7日間": timedelta(days=7),
    "過去30日間": timedelta(days=30),
    "すべて": None,
}
HISTORY_RESULT_OPTIONS = ("すべて", "成功", "失敗", "取り消し")
INCIDENT_SEVERITY_OPTIONS = ("すべて", "失敗", "エラー", "重大")
WEB_TAB_LABELS = ("概要", "推移", "セッション", "操作履歴", "障害", "改善レポート", "タスク", "ログ")
RESULT_FILTER_KEYS = {
    "すべて": "all",
    "成功": "ok",
    "失敗": "failed",
    "取り消し": "cancelled",
    "エラー": "error",
    "重大": "critical",
}


def expected_task_root(task: str) -> Path:
    return REPOSITORY_ROOT if task in {"SMAI-Server-Analytics", "SMAI-Incident-Automation"} else PROJECT_ROOT


def read_json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


def read_events(limit: int = 200) -> list[dict[str, object]]:
    if not EVENT_LOG.is_file():
        return []
    events: list[dict[str, object]] = []
    try:
        lines = EVENT_LOG.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    for line in lines[-max(0, limit) :]:
        try:
            value = json.loads(line)
        except (TypeError, ValueError):
            continue
        if isinstance(value, dict):
            events.append(value)
    return list(reversed(events))


def parse_timestamp(value: object) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed


def format_timestamp(value: object) -> str:
    parsed = parse_timestamp(value)
    return parsed.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z") if parsed is not None else "時刻不明"


def compact_timestamp(value: object) -> str:
    parsed = parse_timestamp(value)
    return parsed.astimezone().strftime("%H:%M:%S") if parsed is not None else "時刻不明"


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


def client_type(value: object) -> str:
    normalized = str(value or "").strip().casefold()
    if normalized in {"tablet", "ipad"} or "tablet" in normalized:
        return "tablet"
    if normalized in {"smartphone", "phone", "mobile", "iphone", "android"}:
        return "smartphone"
    if normalized in {"desktop", "pc", "windows", "macos", "linux", "web"}:
        return "desktop"
    return "unknown"


def session_details(session_id: object, value: object) -> dict[str, str]:
    if isinstance(value, dict):
        raw_client_type = value.get("client_type") or value.get("device_type") or value.get("platform")
        return {
            "session_id": str(session_id),
            "last_seen_at": str(value.get("last_seen_at") or ""),
            "user_id": str(value.get("user_id") or ""),
            "profile_name": str(value.get("profile_name") or ""),
            "device_id": str(value.get("device_id") or ""),
            "client_type": client_type(raw_client_type),
            "connection_state": str(value.get("connection_state") or "unknown"),
        }
    return {
        "session_id": str(session_id),
        "last_seen_at": str(value or ""),
        "user_id": "",
        "profile_name": "",
        "device_id": "",
        "client_type": "unknown",
        "connection_state": "unknown",
    }


def heartbeat_status(value: object, *, now: datetime | None = None) -> str:
    parsed = parse_timestamp(value)
    if parsed is None:
        return "unknown"
    seconds = ((now or datetime.now(UTC)).astimezone(UTC) - parsed.astimezone(UTC)).total_seconds()
    return "ok" if seconds <= 90 else "degraded"


def session_connection_status(session: Mapping[str, str], *, now: datetime | None = None) -> str:
    connection = str(session.get("connection_state") or "").strip().casefold()
    if connection in {"critical", "failed", "error"}:
        return "critical"
    if connection in {"degraded", "disconnected", "offline", "closed", "stale"}:
        return "degraded"
    return heartbeat_status(session.get("last_seen_at"), now=now)


def worst_status(*statuses: str) -> str:
    return max(statuses or ("unknown",), key=lambda value: STATUS_PRIORITY.get(value.casefold(), 3))


def health_score(overall: object) -> int:
    return {"healthy": 100, "degraded": 62, "critical": 18}.get(str(overall or "").casefold(), 0)


def status_label(status: object) -> str:
    normalized = str(status or "unknown").casefold()
    return STATUS_LABELS.get(normalized, STATUS_LABELS["unknown"])


def status_color(status: object) -> str:
    normalized = str(status or "unknown").casefold()
    return STATUS_COLORS.get(normalized, STATUS_COLORS["unknown"])


def filter_key(value: object) -> str:
    return RESULT_FILTER_KEYS.get(str(value), str(value))


def event_within_window(value: object, window: str, *, now: datetime | None = None) -> bool:
    duration = TIME_WINDOW_OPTIONS.get(window)
    if duration is None:
        return window == "すべて"
    parsed = parse_timestamp(value)
    if parsed is None:
        return False
    current = (now or datetime.now(UTC)).astimezone(UTC)
    return parsed.astimezone(UTC) >= current - duration


def service_status(checks: Mapping[str, str], *keywords: str) -> str:
    matches = [status for name, status in checks.items() if any(keyword.casefold() in name.casefold() for keyword in keywords)]
    return worst_status(*matches) if matches else "unknown"


def recent_logs() -> list[str]:
    files = [path for root in LOG_ROOTS if root.is_dir() for path in root.glob("*.log")]
    try:
        files.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    except OSError:
        return ["ログファイルを読み取れません"]
    lines: list[str] = []
    for path in files[:5]:
        try:
            lines.extend([f"[{path.name}]", *path.read_text(encoding="utf-8", errors="replace").splitlines()[-12:]])
        except OSError:
            continue
    return lines[-100:] or ["直近ログはありません"]


def task_rows() -> list[dict[str, str]]:
    try:
        return task_monitor.collect(
            TASKS,
            runtime_root=RUNTIME_ROOT,
            expected_root=expected_task_root,
            backup_state=read_json(BACKUP_SMOKE_STATE),
        )
    except (OSError, ValueError, TypeError):
        return [
            {
                "name": "Task Scheduler",
                "status": "unknown",
                "last_run_at": "",
                "next_run_at": "",
                "last_result": "",
                "detail": "タスク状態を取得できません",
                "source": "scheduler",
            }
        ]


def run_health_check() -> str:
    """Run the existing local probe without exposing subprocess output to browsers."""

    if os.environ.get("SMAI_ANALYTICS_TEST_SKIP_HEALTH_PROBE") == "1":
        return ""
    try:
        result = subprocess.run(
            [sys.executable, str(REPOSITORY_ROOT / "health.py")],
            timeout=4,
            check=False,
            capture_output=True,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "health.py を起動できないため、直近スナップショットを表示しています"
    return "" if result.returncode == 0 else "health.py が失敗したため、直近スナップショットを表示しています"


def collect_operations_snapshot() -> dict[str, object]:
    """Collect bounded, fail-closed operational data for one web refresh."""

    health_note = run_health_check()
    snapshot = read_json(SNAPSHOT)
    overall = str(snapshot.get("overall") or "unknown").casefold()
    raw_checks = snapshot.get("checks")
    checks = [item for item in raw_checks if isinstance(item, dict)] if isinstance(raw_checks, list) else []
    check_statuses = {
        str(item.get("name") or "").casefold(): str(item.get("status") or "unknown").casefold()
        for item in checks
    }
    raw_storage = snapshot.get("storage")
    storage = [item for item in raw_storage if isinstance(item, dict)] if isinstance(raw_storage, list) else []
    activity = read_json(ACTIVITY)
    raw_sessions = activity.get("sessions")
    raw_operations = activity.get("operations")
    activity_available = ACTIVITY.is_file() and isinstance(raw_sessions, dict) and isinstance(raw_operations, dict)
    sessions = [session_details(session_id, value) for session_id, value in raw_sessions.items()] if activity_available else []
    events = read_events()
    try:
        reports = incident_automation.report_rows()
    except (OSError, ValueError, TypeError):
        reports = []
    try:
        rollups = telemetry.read_health_rollups(RUNTIME_ROOT, window=timedelta(days=30))
    except (OSError, ValueError, TypeError):
        rollups = []
    connection_history = connection_watch.read(CONNECTION_WATCH_STATE)
    try:
        task_history = task_monitor.read_observations(RUNTIME_ROOT, window=timedelta(days=30))
    except (OSError, ValueError, TypeError):
        task_history = []
    return {
        "health_note": health_note,
        "overall": overall,
        "checked_at": snapshot.get("checked_at"),
        "checks": checks,
        "check_statuses": check_statuses,
        "storage": storage,
        "activity_available": activity_available,
        "session_count": len(raw_sessions) if activity_available else None,
        "operation_count": len(raw_operations) if activity_available else None,
        "sessions": sessions,
        "tasks": task_rows(),
        "events": events,
        "reports": reports,
        "logs": recent_logs(),
        "rollups": rollups,
        "connection_history": connection_history,
        "task_history": task_history,
    }


if st is not None:

    @st.cache_data(ttl=5, show_spinner=False)
    def cached_operations_snapshot() -> dict[str, object]:
        return collect_operations_snapshot()

else:

    def cached_operations_snapshot() -> dict[str, object]:
        return collect_operations_snapshot()


def _status_pill(status: object) -> str:
    normalized = str(status or "unknown").casefold()
    color = status_color(normalized)
    label = html.escape(status_label(normalized))
    return f'<span class="status-pill" style="border-color:{color};color:{color}">{label}</span>'


def _narrative(overall: str) -> tuple[str, str]:
    if overall == "healthy":
        return "運用は安定", "接続・画面応答・ローカル保存の直近チェックは正常です。"
    if overall == "degraded":
        return "一部の観測点に注意", "黄色のチェックまたはタスクを確認してください。"
    if overall == "critical":
        return "サービス継続性に影響", "入口への接続とStreamlitプロセスを最優先で確認してください。"
    return "監視証跡を取得できません", "現在の状態を正常と判断できるスナップショットがありません。"


def _render_styles() -> None:
    assert st is not None
    st.markdown(
        """
        <style>
          .stApp { background: #070D19; color: #E5EDF7; }
          [data-testid="stHeader"] { background: rgba(7, 13, 25, 0.94); }
          [data-testid="stMainBlockContainer"], .block-container {
            max-width: none;
            padding: 1.15rem 2.2rem 2.5rem;
          }
          [data-testid="stMetric"] {
            background: linear-gradient(145deg, #14243d, #0e1a2e);
            border: 1px solid #354763;
            border-radius: 14px;
            min-height: 108px;
            padding: 15px 18px;
          }
          [data-testid="stMetricLabel"] { color: #AAB8C8; font-weight: 700; }
          [data-testid="stMetricValue"] { color: #F8FBFF; }
          button[kind="secondary"] { border-color: #3b587d; color: #DCEBFF; }
          .status-card, .ops-panel, .topology-node, .brand-block, .overview-route {
            background: linear-gradient(145deg, #14243d, #0e1a2e);
            border: 1px solid #354763;
            border-radius: 14px;
          }
          .brand-block { min-height: 110px; padding: 10px 16px; }
          .brand-wordmark { display: block; height: 78px; max-width: min(100%, 500px); object-fit: contain; object-position: left center; }
          .brand-copy { color: #AAB8C8; font-size: 0.86rem; margin: 2px 0 0; }
          .status-card { align-items: center; display: flex; gap: 12px; min-height: 112px; padding: 14px 16px; }
          .status-card-copy { min-width: 0; }
          .status-mascot { height: 64px; object-fit: contain; width: 64px; }
          .status-card h2 { color: #F8FBFF; font-size: 1.14rem; margin: 10px 0 6px; }
          .status-card p { color: #AAB8C8; margin: 0; }
          .status-pill {
            border: 1px solid;
            border-radius: 999px;
            display: inline-block;
            font-size: 0.75rem;
            font-weight: 800;
            letter-spacing: 0.07em;
            padding: 4px 10px;
          }
          .panel-kicker { color: #60A5FA; font-size: 0.72rem; font-weight: 800; letter-spacing: 0.1em; margin-bottom: 2px; }
          .panel-title { color: #F8FBFF; font-size: 1.06rem; font-weight: 800; margin: 0 0 4px; }
          .panel-caption, .section-note { color: #AAB8C8; font-size: 0.88rem; margin: 0 0 12px; }
          .topology-node { min-height: 164px; padding: 12px; text-align: center; }
          .topology-image { display: block; height: 60px; margin: 0 auto 4px; object-fit: contain; width: 76px; }
          .topology-node strong { color: #F8FBFF; display: block; margin-top: 3px; }
          .topology-node small { color: #AAB8C8; }
          .overview-route { min-height: 116px; padding: 15px 16px; }
          .overview-route h3 { color: #F8FBFF; font-size: 1rem; margin: 0 0 7px; }
          .overview-route p { color: #AAB8C8; font-size: 0.88rem; margin: 0; }
          .overview-route strong { color: #22D3EE; display: block; font-size: 0.74rem; letter-spacing: 0.08em; margin-bottom: 8px; }
          .gauge-wrap { align-items: center; display: flex; gap: 20px; min-height: 205px; }
          .gauge {
            align-items: center;
            background: conic-gradient(var(--health-color) calc(var(--score) * 1%), #253a58 0);
            border-radius: 50%;
            display: flex;
            height: 142px;
            justify-content: center;
            min-width: 142px;
            position: relative;
          }
          .gauge::before { background: #0e1a2e; border-radius: 50%; content: ""; height: 112px; position: absolute; width: 112px; }
          .gauge-value { color: #F8FBFF; font-size: 1.9rem; font-weight: 800; position: relative; z-index: 1; }
          .gauge-copy h3 { color: #F8FBFF; margin: 0 0 8px; }
          .gauge-copy p { color: #AAB8C8; margin: 0; }
          [data-baseweb="tab-list"] { gap: 5px; }
          [data-baseweb="tab"] { color: #AAB8C8; font-weight: 750; padding-left: 16px; padding-right: 16px; }
          [aria-selected="true"][data-baseweb="tab"] { color: #22D3EE; }
          [data-testid="stDataFrame"] { font-size: 0.94rem; }
          @media (min-width: 2200px) {
            [data-testid="stMainBlockContainer"], .block-container { padding-left: 3rem; padding-right: 3rem; }
            [data-testid="stMetric"] { min-height: 136px; padding: 21px 24px; }
            .topology-node { min-height: 168px; }
          }
          @media (max-width: 760px) {
            .block-container { padding-left: 0.8rem; padding-right: 0.8rem; }
            [data-testid="stMetric"] { min-height: 92px; padding: 12px; }
            .gauge-wrap { align-items: flex-start; flex-direction: column; }
            .topology-node { min-height: 128px; padding: 9px; }
            [data-baseweb="tab"] { font-size: 0.83rem; padding-left: 9px; padding-right: 9px; }
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _panel_heading(title: str, subtitle: str, *, kicker: str = "OPERATIONS") -> None:
    assert st is not None
    st.markdown(
        f'<p class="panel-kicker">{html.escape(kicker)}</p><p class="panel-title">{html.escape(title)}</p><p class="panel-caption">{html.escape(subtitle)}</p>',
        unsafe_allow_html=True,
    )


def _topology_tile(index: int) -> bytes | str | None:
    if not TOPOLOGY_SPRITE.is_file():
        return None
    try:
        from PIL import Image

        with Image.open(TOPOLOGY_SPRITE) as source:
            source = source.convert("RGBA")
            tile_width, tile_height = source.width // 2, source.height // 2
            column, row = index % 2, index // 2
            tile = source.crop((column * tile_width, row * tile_height, (column + 1) * tile_width, (row + 1) * tile_height))
            bounds = tile.getchannel("A").point(lambda value: 255 if value >= 48 else 0).getbbox()
            if bounds is not None:
                tile = tile.crop(bounds)
            tile.thumbnail((160, 160), Image.Resampling.LANCZOS)
            output = BytesIO()
            tile.save(output, format="PNG")
            return output.getvalue()
    except (OSError, ValueError, ImportError):
        return str(TOPOLOGY_SPRITE)


def _image_data_uri(image: bytes | str | Path | None) -> str:
    if image is None:
        return ""
    if isinstance(image, bytes):
        return "data:image/png;base64," + b64encode(image).decode("ascii")
    path = Path(image)
    if not path.is_file():
        return ""
    mime_type = "image/png" if path.suffix.casefold() == ".png" else "image/jpeg"
    try:
        return f"data:{mime_type};base64," + b64encode(path.read_bytes()).decode("ascii")
    except OSError:
        return ""


def _downsample_rows(rows: list[dict[str, object]], *, maximum: int) -> list[dict[str, object]]:
    if len(rows) <= maximum:
        return rows
    stride = max(1, (len(rows) + maximum - 1) // maximum)
    sampled = rows[::stride]
    if sampled[-1] != rows[-1]:
        sampled.append(rows[-1])
    return sampled


def _rollups_for_window(data: Mapping[str, object], window: str) -> list[dict[str, object]]:
    duration = TIME_WINDOW_OPTIONS.get(window, timedelta(hours=24))
    raw_rows = data.get("rollups")
    rows = [row for row in raw_rows if isinstance(row, dict)] if isinstance(raw_rows, list) else []
    if duration is None:
        return rows
    now = datetime.now(UTC)
    return [row for row in rows if (timestamp := parse_timestamp(row.get("bucket_start"))) is not None and timestamp.astimezone(UTC) >= now - duration]


def _session_statuses(sessions: list[dict[str, str]]) -> dict[str, str]:
    return {
        client: worst_status(*(session_connection_status(item) for item in sessions if item.get("client_type") == client))
        if any(item.get("client_type") == client for item in sessions)
        else "unknown"
        for client in connection_watch.CLIENT_TYPES
    }


def _render_header(data: Mapping[str, object]) -> None:
    assert st is not None
    brand, status, controls = st.columns((6, 3, 1))
    with brand:
        wordmark = _image_data_uri(ANALYTICS_WORDMARK)
        brand_image = f'<img class="brand-wordmark" src="{wordmark}" alt="SMAI Analytics">' if wordmark else "<h1>SMAI Analytics</h1>"
        st.markdown(f'<div class="brand-block">{brand_image}<p class="brand-copy">Operations Console / 常時ローカル監視 / 信頼済みプライベートLAN閲覧</p></div>', unsafe_allow_html=True)
    with status:
        title, detail = _narrative(str(data["overall"]))
        mascot = _image_data_uri(ANALYTICS_MASCOT)
        mascot_image = f'<img class="status-mascot" src="{mascot}" alt="SMAI Analytics mascot">' if mascot else ""
        st.markdown(f'<div class="status-card">{mascot_image}<div class="status-card-copy">{_status_pill(data["overall"])}<h2>{html.escape(title)}</h2><p>{html.escape(detail)}</p></div></div>', unsafe_allow_html=True)
    with controls:
        st.caption("表示更新")
        if st.button("今すぐ", key="refresh_now", use_container_width=True):
            cached_operations_snapshot.clear()
            st.rerun()


def _render_metrics(data: Mapping[str, object]) -> None:
    assert st is not None
    sessions = "—" if data["session_count"] is None else str(data["session_count"])
    operations = "—" if data["operation_count"] is None else str(data["operation_count"])
    columns = st.columns(4)
    columns[0].metric("ヘルススコア", f"{health_score(data['overall'])} / 100", status_label(data["overall"]))
    columns[1].metric("接続セッション", sessions, "現在の接続状態")
    columns[2].metric("実行中の処理", operations, "現在の実行状態")
    columns[3].metric("最終確認", compact_timestamp(data["checked_at"]), format_timestamp(data["checked_at"]))


def _render_topology_node(column: object, *, label: str, detail: str, status: str, image: bytes | str | None = None) -> None:
    assert st is not None
    with column:
        image_uri = _image_data_uri(image)
        image_tag = f'<img class="topology-image" src="{image_uri}" alt="{html.escape(label)}">' if image_uri else ""
        st.markdown(
            f'<div class="topology-node">{image_tag}<strong>{html.escape(label)}</strong><small>{html.escape(detail)}</small><br><br>{_status_pill(status)}</div>',
            unsafe_allow_html=True,
        )


def _check_rows(data: Mapping[str, object]) -> list[dict[str, str]]:
    checks = data.get("checks")
    return [
        {
            "レベル": str(item.get("level") or "—"),
            "チェック": str(item.get("name") or "—"),
            "状態": status_label(item.get("status")),
            "詳細": str(item.get("detail") or item.get("message") or "—"),
            "応答": f"{item.get('latency_ms')} ms" if isinstance(item.get("latency_ms"), int) else "—",
        }
        for item in checks
        if isinstance(item, dict)
    ] if isinstance(checks, list) else []


def _render_gauge(data: Mapping[str, object]) -> None:
    assert st is not None
    score = health_score(data["overall"])
    color = status_color(data["overall"])
    title, detail = _narrative(str(data["overall"]))
    st.markdown(
        f'<div class="ops-panel gauge-wrap"><div class="gauge" style="--score:{score};--health-color:{color}"><span class="gauge-value">{score}</span></div><div class="gauge-copy"><p class="panel-kicker">システム健全性</p><h3>{html.escape(title)}</h3><p>{html.escape(detail)}</p><p style="margin-top:12px">{_status_pill(data["overall"])}</p></div></div>',
        unsafe_allow_html=True,
    )


def _next_check(data: Mapping[str, object]) -> tuple[str, str, str]:
    """Return a concise, deterministic next-step message for the overview."""
    overall = str(data.get("overall") or "unknown").casefold()
    if overall == "critical":
        return "障害", "L1接続と本体Streamlitの稼働状況を優先して確認してください。", "障害タブで失敗記録を確認"
    if overall == "degraded":
        return "推移", "黄色の検査項目と直近の変化を確認してください。", "推移タブでL1〜L3の詳細を確認"
    if overall == "unknown":
        return "推移", "監視証跡を読めません。状態を正常とは判断していません。", "推移タブで検査証跡を確認"

    tasks = data.get("tasks")
    task_statuses = [str(row.get("status") or "unknown") for row in tasks if isinstance(row, dict)] if isinstance(tasks, list) else []
    if task_statuses and worst_status(*task_statuses) not in {"healthy", "ok"}:
        return "タスク", "Scheduled Taskまたは復元検証に要確認の記録があります。", "タスクタブで鮮度と実行結果を確認"
    return "概要", "直近の監視結果に緊急の要確認項目はありません。", "詳細な推移は推移タブで確認"


def _render_overview_route(tab_name: str, title: str, description: str) -> None:
    assert st is not None
    st.markdown(
        f'<div class="overview-route"><strong>{html.escape(tab_name)}</strong><h3>{html.escape(title)}</h3><p>{html.escape(description)}</p></div>',
        unsafe_allow_html=True,
    )


def _render_overview(data: Mapping[str, object]) -> None:
    assert st is not None
    checks = data.get("check_statuses")
    check_statuses = checks if isinstance(checks, dict) else {}
    storage = data.get("storage")
    storage_rows = [item for item in storage if isinstance(item, dict)] if isinstance(storage, list) else []
    storage_status = worst_status(*(str(item.get("status") or "unknown") for item in storage_rows))
    health, next_step = st.columns((5, 7))
    with health:
        _render_gauge(data)
    with next_step:
        destination, guidance, route = _next_check(data)
        _panel_heading("次に確認", "状態に応じて、次に開くべき詳細画面を一つだけ案内します。", kicker="確認ガイド")
        st.markdown(
            f'<div class="overview-route"><strong>{html.escape(destination)} タブ</strong><h3>{html.escape(guidance)}</h3><p>{html.escape(route)}</p></div>',
            unsafe_allow_html=True,
        )
        st.caption("詳細な時系列、検査表、復元準備、端末別の状況は下記の専用タブへ分散しています。")

    _panel_heading("サービス概要", "概要では現在のサービス状態だけを表示します。端末別の接続はセッション、検査履歴は推移で確認します。")
    services = st.columns(3)
    _render_topology_node(services[0], label="SMAI UI", detail="SMAI本体の画面サービス", status=service_status(check_statuses, "streamlit"), image=_topology_tile(1))
    _render_topology_node(services[1], label="Runtime", detail="ローカル状態・バックアップ", status=storage_status, image=_topology_tile(2))
    _render_topology_node(services[2], label="Analytics", detail="運用コンソール", status=str(data["overall"]), image=_topology_tile(3))

    _panel_heading("詳細を開く", "同じ情報をOverviewへ繰り返して載せず、用途別のタブで確認します。", kicker="OPERATIONS MAP")
    routes = st.columns(4)
    with routes[0]:
        _render_overview_route("推移", "検査・応答・容量の履歴", "L1〜L3の最新検査表と時系列を確認します。")
    with routes[1]:
        _render_overview_route("セッション", "端末ごとの接続状況", "PC・スマートフォン・タブレットの観測を確認します。")
    with routes[2]:
        _render_overview_route("改善レポート", "復元の準備状況", "復元検証、容量、履歴カバレッジを確認します。")
    with routes[3]:
        _render_overview_route("タスク", "実行鮮度と失敗理由", "Scheduled Taskの結果と期限を確認します。")


def _render_trends(data: Mapping[str, object]) -> None:
    assert st is not None
    controls, coverage = st.columns((2, 5))
    with controls:
        selected = st.selectbox("表示期間", tuple(TIME_WINDOW_OPTIONS)[:3], key="trends_window")
    rollups = _rollups_for_window(data, selected)
    duration = TIME_WINDOW_OPTIONS[selected] or timedelta(hours=24)
    summary = telemetry.window_summary(rollups, window=duration)
    with coverage:
        st.caption(f"履歴カバレッジ: {summary['coverage_percent']}%  /  {summary['available_buckets']} / {summary['expected_buckets']} 枠。欠損は正常として数えません。")

    _panel_heading("LATEST CHECK MATRIX", "現在のL1〜L3検査結果です。時系列の変化はこの下のグラフで確認します。", kicker="CURRENT EVIDENCE")
    check_rows = _check_rows(data)
    if check_rows:
        st.dataframe(check_rows, use_container_width=True, hide_index=True)
    else:
        st.warning("ヘルスチェックの証跡を読み取れません。正常とは判定していません。")

    _panel_heading("HEALTH HISTORY", "overallとL1〜L3の状態スコアを5分集計で表示します。", kicker="TRENDS")
    health_rows: list[dict[str, object]] = []
    for row in rollups:
        timestamp = parse_timestamp(row.get("bucket_start"))
        health_rows.append(
            {
                "時刻": timestamp.astimezone().strftime("%m/%d %H:%M") if timestamp is not None else "時刻不明",
                "overall": health_score(telemetry.status_from_counts(row.get("overall"))),
                "L1": health_score(telemetry.level_status(row, "L1")),
                "L2": health_score(telemetry.level_status(row, "L2")),
                "L3": health_score(telemetry.level_status(row, "L3")),
            }
        )
    if health_rows:
        st.line_chart(_downsample_rows(health_rows, maximum=96), x="時刻", y=("overall", "L1", "L2", "L3"), height=280, use_container_width=True)
    else:
        st.info("選択期間のhealth履歴はまだありません。")

    latency, storage = st.columns(2)
    with latency:
        _panel_heading("RESPONSE LATENCY", "Streamlit health/pageの5分p95応答時間です。", kicker="LATENCY")
        rows: list[dict[str, object]] = []
        for row in rollups:
            timestamp = parse_timestamp(row.get("bucket_start"))
            values = row.get("latency_ms")
            if not isinstance(values, dict):
                continue
            rows.append(
                {
                    "時刻": timestamp.astimezone().strftime("%m/%d %H:%M") if timestamp is not None else "時刻不明",
                    "Streamlit health p95": int(values.get("Streamlit health", {}).get("p95_ms", 0)) if isinstance(values.get("Streamlit health"), dict) else 0,
                    "Streamlit page p95": int(values.get("Streamlit page", {}).get("p95_ms", 0)) if isinstance(values.get("Streamlit page"), dict) else 0,
                }
            )
        if rows:
            st.line_chart(_downsample_rows(rows, maximum=96), x="時刻", y=("Streamlit health p95", "Streamlit page p95"), height=230, use_container_width=True)
        else:
            st.info("応答時間の履歴はまだありません。")
    with storage:
        _panel_heading("STORAGE HEADROOM", "SMAIデータとRuntimeの空き容量率です。", kicker="CAPACITY")
        rows = []
        for row in rollups:
            timestamp = parse_timestamp(row.get("bucket_start"))
            measures = row.get("storage")
            values = {str(item.get("name")): item.get("free_percent") for item in measures if isinstance(item, dict)} if isinstance(measures, list) else {}
            rows.append(
                {
                    "時刻": timestamp.astimezone().strftime("%m/%d %H:%M") if timestamp is not None else "時刻不明",
                    "SMAI data": values.get("SMAI data"),
                    "Runtime": values.get("Runtime"),
                }
            )
        if rows:
            st.line_chart(_downsample_rows(rows, maximum=96), x="時刻", y=("SMAI data", "Runtime"), height=230, use_container_width=True)
        else:
            st.info("保存容量の履歴はまだありません。")

    _panel_heading("JOB FRESHNESS", "Schedulerと復元検証の観測履歴です。", kicker="TASK HISTORY")
    history = data.get("task_history")
    task_rows: list[dict[str, object]] = []
    if isinstance(history, list):
        for row in history:
            if not isinstance(row, dict):
                continue
            observed = parse_timestamp(row.get("observed_at"))
            tasks = row.get("tasks")
            statuses = [str(item.get("status") or "unknown") for item in tasks if isinstance(item, dict)] if isinstance(tasks, list) else []
            task_rows.append(
                {
                    "観測時刻": observed.astimezone().strftime("%m/%d %H:%M") if observed is not None else "時刻不明",
                    "鮮度スコア": health_score(worst_status(*statuses)),
                    "対象数": len(statuses),
                }
            )
    if task_rows:
        st.line_chart(task_rows, x="観測時刻", y="鮮度スコア", height=180, use_container_width=True)
    else:
        st.info("タスク鮮度の履歴はまだありません。")


def _render_connections(data: Mapping[str, object]) -> None:
    assert st is not None
    _panel_heading("端末接続状況", "端末種別ごとの現在接続数とAnalytics観測開始後の累計です。", kicker="SESSIONS")
    sessions = [item for item in data.get("sessions", []) if isinstance(item, dict)] if isinstance(data.get("sessions"), list) else []
    history = data.get("connection_history")
    state = history.get("state") if isinstance(history, dict) else {}
    summary = connection_watch.summary(state) if isinstance(state, dict) else connection_watch.summary({})
    active = {client: sum(1 for session in sessions if session.get("client_type") == client and session_connection_status(session) == "ok") for client in connection_watch.CLIENT_TYPES}
    metrics = st.columns(3)
    for column, client in zip(metrics, connection_watch.CLIENT_TYPES):
        cumulative = summary.get("cumulative", {}).get(client, 0) if isinstance(summary.get("cumulative"), dict) else 0
        unlinked = sum(1 for session in sessions if session.get("client_type") == client and session_connection_status(session) == "ok" and not session.get("device_id"))
        detail = f"累計 {cumulative}台" + (f" / ID未連携 {unlinked}" if unlinked else "")
        column.metric(f"{CLIENT_TYPE_LABELS[client]} / 現在接続", f"{active[client]}台", detail)
    if not bool(data.get("activity_available")):
        st.warning("activity state を読み取れません。接続がない、とは判断していません。")
    else:
        rows = []
        for session in sessions:
            communication = session_connection_status(session)
            user = session["profile_name"] or session["user_id"] or compact_id(session["session_id"])
            if session["profile_name"] and session["user_id"]:
                user = f"{session['profile_name']} / {compact_id(session['user_id'])}"
            rows.append(
                {
                    "ユーザー / プロフィール": user,
                    "端末種別": CLIENT_TYPE_LABELS.get(session["client_type"], "種別不明"),
                    "最終通信": f"{relative_time(session['last_seen_at'])} / {format_timestamp(session['last_seen_at'])}",
                    "端末擬似ID": compact_id(session["device_id"]) if session["device_id"] else "—",
                    "状態": status_label(communication),
                }
            )
        st.markdown("#### セッション一覧")
        if rows:
            st.dataframe(rows, use_container_width=True, hide_index=True)
        else:
            st.info("接続中のセッションはありません。")

    st.markdown("#### 接続観測履歴")
    raw_events = state.get("events") if isinstance(state, dict) else []
    event_rows = [
        {
            "観測時刻": format_timestamp(item.get("observed_at")),
            "端末種別": CLIENT_TYPE_LABELS.get(str(item.get("client_type") or "unknown"), "種別不明"),
            "観測結果": str(item.get("event") or "—"),
            "状態": status_label(item.get("status")),
            "セッション": compact_id(item.get("session_id")),
        }
        for item in reversed(raw_events)
        if isinstance(item, dict)
    ] if isinstance(raw_events, list) else []
    if event_rows:
        st.dataframe(event_rows, use_container_width=True, hide_index=True)
    else:
        st.info("接続観測履歴はまだありません。消失は切断と推測しません。")


def _render_activity_history(data: Mapping[str, object]) -> None:
    assert st is not None
    _panel_heading("操作履歴", "監査イベントを期間・結果・ユーザーID・操作名で絞り込みます。", kicker="ACTIVITY HISTORY")
    period, result, user, action = st.columns((2, 2, 3, 3))
    with period:
        selected_window = st.selectbox("期間", tuple(TIME_WINDOW_OPTIONS), key="activity_window")
    with result:
        selected_result = st.selectbox("結果", HISTORY_RESULT_OPTIONS, key="activity_result")
    with user:
        user_query = st.text_input("ユーザーID", key="activity_user").strip().casefold()
    with action:
        action_query = st.text_input("操作名", key="activity_action").strip().casefold()
    result_key = filter_key(selected_result)
    events = [item for item in data.get("events", []) if isinstance(item, dict)] if isinstance(data.get("events"), list) else []
    matched = [
        event
        for event in events
        if event_within_window(event.get("timestamp"), selected_window)
        and (result_key == "all" or str(event.get("result") or "").casefold() == result_key)
        and (not user_query or user_query in str(event.get("user_id") or "").casefold())
        and (not action_query or action_query in str(event.get("action") or "").casefold())
    ]
    successes = sum(1 for event in matched if str(event.get("result") or "").casefold() == "ok")
    failures = sum(1 for event in matched if str(event.get("result") or "").casefold() in {"failed", "error", "critical"})
    cancelled = sum(1 for event in matched if str(event.get("result") or "").casefold() == "cancelled")
    metrics = st.columns(3)
    metrics[0].metric("直近イベント", str(len(matched)), "最大200件の監査記録")
    metrics[1].metric("成功", str(successes), "成功した操作")
    metrics[2].metric("失敗 / 取消", str(failures + cancelled), f"失敗 {failures} / 取消 {cancelled}")
    rows = [
        {
            "時刻": format_timestamp(event.get("timestamp")),
            "ユーザー": compact_id(event.get("user_id")),
            "操作": str(event.get("action") or "—"),
            "対象": str(event.get("target") or "—"),
            "結果": status_label(event.get("result")),
            "端末": compact_id(event.get("device_id")),
            "所要時間": f"{event.get('duration_ms')} ms" if event.get("duration_ms") not in {None, ""} else "—",
        }
        for event in matched
    ]
    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True)
    elif events:
        st.info("条件に一致する操作履歴はありません。")
    else:
        st.info("操作履歴はまだありません。SMAI本体からの監査イベント連携後に表示されます。")


def _render_incidents(data: Mapping[str, object]) -> None:
    assert st is not None
    _panel_heading("障害状況", "failed / error / critical の監査イベントを失敗種別と期間で確認します。", kicker="INCIDENTS")
    period, severity = st.columns(2)
    with period:
        selected_window = st.selectbox("期間", tuple(TIME_WINDOW_OPTIONS), index=1, key="incident_window")
    with severity:
        selected_severity = st.selectbox("重要度", INCIDENT_SEVERITY_OPTIONS, key="incident_severity")
    selected_result = filter_key(selected_severity)
    source = [
        event
        for event in data.get("events", [])
        if isinstance(event, dict) and str(event.get("result") or "").casefold() in {"failed", "error", "critical"}
    ] if isinstance(data.get("events"), list) else []
    matched = [
        event
        for event in source
        if event_within_window(event.get("timestamp"), selected_window)
        and (selected_result == "all" or str(event.get("result") or "").casefold() == selected_result)
    ]
    critical = sum(1 for event in matched if str(event.get("result") or "").casefold() == "critical")
    latest = relative_time(matched[0].get("timestamp")) if matched else "記録なし"
    metrics = st.columns(3)
    metrics[0].metric("該当件数", str(len(matched)), "現在の絞り込み結果")
    metrics[1].metric("直近の記録", latest, "復旧状況はレポートで確認")
    metrics[2].metric("重大", str(critical), "critical の件数")
    rows = [
        {
            "時刻": format_timestamp(event.get("timestamp")),
            "操作": str(event.get("action") or "—"),
            "対象": str(event.get("target") or "—"),
            "結果": status_label(event.get("result")),
        }
        for event in matched
    ]
    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True)
    elif source:
        st.info("条件に一致する障害はありません。")
    else:
        st.success("現在の監査イベントに failed / error / critical はありません。")


def _render_reports(data: Mapping[str, object]) -> None:
    assert st is not None
    _panel_heading("RECOVERY READINESS", "復元検証、容量、履歴カバレッジをここで確認します。", kicker="RECOVERY")
    tasks = data.get("tasks")
    smoke = next(
        (
            row
            for row in tasks
            if isinstance(row, dict) and row.get("name") == "Backup Restore Smoke"
        ),
        {},
    ) if isinstance(tasks, list) else {}
    storage = data.get("storage")
    storage_rows = [item for item in storage if isinstance(item, dict)] if isinstance(storage, list) else []
    headroom = min(
        (
            float(item.get("free_percent"))
            for item in storage_rows
            if isinstance(item.get("free_percent"), (int, float))
        ),
        default=None,
    )
    summary = telemetry.window_summary(_rollups_for_window(data, "過去24時間"), window=timedelta(hours=24))
    metrics = st.columns(3)
    metrics[0].metric("復元検証", status_label(smoke.get("status")), str(smoke.get("detail") or "記録なし"))
    metrics[1].metric("最小空き率", "—" if headroom is None else f"{headroom:.1f}%", "SMAI data / Runtime")
    metrics[2].metric(
        "履歴カバレッジ",
        f"{summary['coverage_percent']}%",
        f"{summary['available_buckets']} / {summary['expected_buckets']} 枠",
    )
    st.caption("復元の実行結果と期限はタスク、容量・healthの時系列は推移タブで詳しく確認できます。")

    _panel_heading("改善レポート", "重大な障害の調査結果を確認します。メール送信は別途SMTP設定がある場合だけです。", kicker="REPORTS")
    reports = data.get("reports")
    rows = [
        {
            "記録時刻": format_timestamp(report.get("reported_at")),
            "調査依頼": compact_id(report.get("request_id"), limit=28),
            "重要度": str(report.get("severity") or "—").upper(),
            "状態": status_label(report.get("status")),
            "改善結果": str(report.get("summary") or "調査結果はまだ記録されていません。"),
        }
        for report in reports
        if isinstance(report, dict)
    ] if isinstance(reports, list) else []
    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.info("改善レポートはまだありません。重大な障害が検知されると、調査結果がここに追加されます。")


def _render_tasks(data: Mapping[str, object]) -> None:
    assert st is not None
    _panel_heading("タスク鮮度", "Schedulerと隔離復元検証の最終成功・実行パス・期限を確認します。", kicker="TASKS")
    tasks = [item for item in data.get("tasks", []) if isinstance(item, dict)] if isinstance(data.get("tasks"), list) else []
    healthy = sum(1 for row in tasks if str(row.get("status") or "").casefold() == "healthy")
    unknown = sum(1 for row in tasks if str(row.get("status") or "").casefold() == "unknown")
    attention = len(tasks) - healthy - unknown
    metrics = st.columns(3)
    metrics[0].metric("予定内", str(healthy), "最終成功・実行パスを確認")
    metrics[1].metric("取得不能", str(unknown), "未登録・権限・記録なし")
    metrics[2].metric("期限超過 / 失敗", str(attention), "復旧または設定を確認")
    rows = [
        {
            "タスク": str(row.get("name") or "—"),
            "鮮度": status_label(row.get("status")),
            "最終実行": format_timestamp(row.get("last_run_at")),
            "次回予定": str(row.get("next_run_at") or "—"),
            "最終結果": str(row.get("last_result") or "—"),
            "判定理由": str(row.get("detail") or "—"),
        }
        for row in tasks
    ]
    st.dataframe(rows, use_container_width=True, hide_index=True)


def _render_logs(data: Mapping[str, object]) -> None:
    assert st is not None
    _panel_heading("ログ一覧", "直近の監視・運用ログを最大100行まで表示します。", kicker="LOGS")
    lines = [str(item) for item in data.get("logs", [])] if isinstance(data.get("logs"), list) else []
    errors = sum(any(token in line.casefold() for token in ("error", "failed", "critical")) for line in lines)
    warnings = sum("warn" in line.casefold() for line in lines)
    sources = sum(1 for line in lines if line.startswith("["))
    metrics = st.columns(3)
    metrics[0].metric("表示行", str(len(lines)), "直近ログの抜粋")
    metrics[1].metric("警告", str(warnings), "warn を含む行")
    metrics[2].metric("異常語", str(errors), f"ログソース {sources}件")
    limit = st.selectbox("表示行数", (25, 50, 100), index=2, key="log_limit")
    st.code("\n".join(lines[-limit:]) if lines else "ログを読み取れません", language="text")


def render_dashboard() -> None:
    assert st is not None
    data = cached_operations_snapshot()
    _render_header(data)
    _render_metrics(data)
    if data["health_note"]:
        st.warning(str(data["health_note"]))
    overview, trends, sessions, activity, incidents, reports, tasks, logs = st.tabs(WEB_TAB_LABELS)
    with overview:
        _render_overview(data)
    with trends:
        _render_trends(data)
    with sessions:
        _render_connections(data)
    with activity:
        _render_activity_history(data)
    with incidents:
        _render_incidents(data)
    with reports:
        _render_reports(data)
    with tasks:
        _render_tasks(data)
    with logs:
        _render_logs(data)
    st.caption(f"5秒ごとに更新 / 最終表示 {datetime.now().astimezone().strftime('%H:%M:%S')} / この画面は閲覧専用です")


def main() -> None:
    if st is None:
        raise RuntimeError("Streamlit is required. Run this app with the SMAI Analytics virtual environment.")
    st.set_page_config(page_title="SMAI Analytics | Operations Console", page_icon="📡", layout="wide", initial_sidebar_state="collapsed")
    _render_styles()

    @st.fragment(run_every=5)
    def live_dashboard() -> None:
        render_dashboard()

    live_dashboard()


if __name__ == "__main__":
    main()
