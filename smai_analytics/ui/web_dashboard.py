"""Read-only SMAI Analytics dashboard for trusted private networks.

This Streamlit surface deliberately owns no SMAI calculation, ranking, or
user-facing application state. It reads stable Operations contracts and runs
the server-local health probe at a bounded interval. The launcher binds it to
a separate port so it never competes with SMAI's primary Streamlit application.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
from base64 import b64encode
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Mapping

from ..monitoring import connection_watch, task_observer, telemetry
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
# Browser sessions only read monitor evidence.  The timed fragment redraws the
# compact summary; detailed evidence is fetched on navigation or explicit refresh.
SNAPSHOT_REFRESH_INTERVAL_SECONDS = 15
SUMMARY_REFRESH_INTERVAL_SECONDS = 15
DETAIL_SNAPSHOT_TTL_SECONDS = 60
HEALTH_SNAPSHOT_STALE_AFTER = timedelta(minutes=10)
ANALYTICS_LOGO = ASSET_ROOT / "smai-analytics-logo-transparent.png"
ANALYTICS_MASCOT = ASSET_ROOT / "smai-analytics-mascot.png"
ANALYTICS_MASCOT_HEADER = ASSET_ROOT / "smai-analytics-mascot-header.png"
ANALYTICS_APP_ICON = ASSET_ROOT / "smai-analytics-app-icon-v3.png"
PWA_COMPONENT_ROOT = Path(__file__).resolve().parent / "pwa_metadata_component"
ANALYTICS_WORDMARK = ASSET_ROOT / "smai-analytics-wordmark-luminous.png"
ANALYTICS_WORDMARK_LARGE_TEXT = ASSET_ROOT / "smai-analytics-wordmark-luminous-large-text-v2.png"
TOPOLOGY_SPRITE = ASSET_ROOT / "smai-topology-devices.png"
TOPOLOGY_SMARTPHONE = ASSET_ROOT / "smai-topology-smartphone-v1.png"
TOPOLOGY_TABLET = ASSET_ROOT / "smai-topology-tablet-v1.png"
TASKS = task_observer.task_names()
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
    "auto_validation_failed": 5,
    "auto_merge_blocked": 5,
    "auto_failed": 5,
    "auto_blocked": 5,
    "auto_merged_validation_failed": 5,
    "auto_deploy_blocked": 5,
    "auto_rollback_failed": 5,
    "degraded": 4,
    "stale": 4,
    "pending_investigation": 4,
    "codex_approved": 4,
    "autofix_approved": 4,
    "autofix_running": 4,
    "auto_patch_ready": 4,
    "autofix_merge_approved": 4,
    "auto_merged_pending_deploy": 4,
    "autofix_deploy_approved": 4,
    "autofix_deploying": 4,
    "auto_rolled_back": 4,
    "unknown": 3,
    "healthy": 1,
    "ok": 1,
    "active": 1,
    "running": 1,
    "ready": 1,
    "auto_applied": 1,
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
    "pending_investigation": "調査待ち",
    "codex_approved": "Codex承認済み",
    "autofix_approved": "Autofix承認済み",
    "autofix_running": "Autofix実行中",
    "auto_patch_ready": "修復確認待ち",
    "autofix_merge_approved": "マージ承認済み",
    "auto_merged_pending_deploy": "マージ済み・反映確認待ち",
    "auto_validation_failed": "自動検証失敗",
    "auto_merge_blocked": "自動マージ停止",
    "auto_failed": "Autofix失敗",
    "auto_blocked": "Autofix停止",
    "auto_merged_validation_failed": "マージ済み・検証失敗",
    "autofix_deploy_approved": "配備承認済み",
    "autofix_deploying": "Analytics配備中",
    "auto_deploy_blocked": "自動配備停止",
    "auto_applied": "自動配備・health確認済み",
    "auto_rolled_back": "自動ロールバック済み",
    "auto_rollback_failed": "ロールバック失敗",
    "auto_cancelled": "Autofix取消",
    "unknown": "不明",
}
STATUS_COLORS = {
    "healthy": "#34D399",
    "ok": "#34D399",
    "active": "#34D399",
    "running": "#34D399",
    "ready": "#34D399",
    "autofix_running": "#38BDF8",
    "autofix_deploying": "#38BDF8",
    "degraded": "#FBBF24",
    "stale": "#FBBF24",
    "autofix_approved": "#FBBF24",
    "auto_patch_ready": "#FBBF24",
    "autofix_merge_approved": "#FBBF24",
    "auto_merged_pending_deploy": "#FBBF24",
    "autofix_deploy_approved": "#FBBF24",
    "auto_rolled_back": "#FBBF24",
    "auto_applied": "#34D399",
    "critical": "#F87171",
    "failed": "#F87171",
    "error": "#F87171",
    "auto_validation_failed": "#F87171",
    "auto_merge_blocked": "#F87171",
    "auto_failed": "#F87171",
    "auto_blocked": "#F87171",
    "auto_merged_validation_failed": "#F87171",
    "auto_deploy_blocked": "#F87171",
    "auto_rollback_failed": "#F87171",
    "auto_cancelled": "#AAB8C8",
    "unknown": "#AAB8C8",
}
TIME_WINDOW_OPTIONS = {
    "過去24時間": timedelta(hours=24),
    "過去7日間": timedelta(days=7),
    "過去30日間": timedelta(days=30),
    "すべて": None,
}
DASHBOARD_HEALTH_WINDOW = timedelta(hours=24)
HISTORY_RESULT_OPTIONS = ("すべて", "成功", "失敗", "取り消し")
INCIDENT_SEVERITY_OPTIONS = ("すべて", "失敗", "エラー", "重大")
WEB_TAB_LABELS = ("DashBoard", "推移", "セッション", "操作履歴", "障害", "改善レポート", "タスク", "ログ")
RESULT_FILTER_KEYS = {
    "すべて": "all",
    "成功": "ok",
    "失敗": "failed",
    "取り消し": "cancelled",
    "エラー": "error",
    "重大": "critical",
}
_SENSITIVE_LOG_VALUE_PATTERN = re.compile(
    r"""(?ix)
    \b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|token|secret|password|passwd|
    authorization|cookie|set-cookie|credential)\b
    \s*(?:=|:\s*(?:bearer\s+)?)\s*(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)
    """
)
_EMAIL_PATTERN = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_WINDOWS_PATH_PATTERN = re.compile(r"(?i)(?:[a-z]:\\|\\\\)[^\s\"'<>]+")
_INTERNAL_IP_PATTERN = re.compile(
    r"\b(?:10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[0-1])(?:\.\d{1,3}){2}|100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])(?:\.\d{1,3}){2})\b"
)
_URL_QUERY_PATTERN = re.compile(r"https?://[^\s?#]+(?:/[^\s?#]*)?\?[^\s]+", re.IGNORECASE)


def expected_task_root(task: str) -> Path:
    return task_observer.expected_task_root(task)


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


def anonymized_identifier(value: object, *, prefix: str) -> str:
    """Return a stable display identifier without exposing an account or session value."""

    raw = str(value or "").strip()
    if not raw:
        return "—"
    return f"{prefix}-{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:10]}"


def sanitize_log_line(value: object) -> str:
    """Remove common secret, identity, address, and path forms from browser-visible logs."""

    text = str(value or "").replace("\x00", "")
    text = _SENSITIVE_LOG_VALUE_PATTERN.sub("[redacted-secret]", text)
    text = _URL_QUERY_PATTERN.sub("[redacted-url-query]", text)
    text = _EMAIL_PATTERN.sub("[redacted-email]", text)
    text = _WINDOWS_PATH_PATTERN.sub("[redacted-path]", text)
    text = _INTERNAL_IP_PATTERN.sub("[redacted-ip]", text)
    return text[:1000]


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
            "display_user_id": anonymized_identifier(value.get("user_id") or session_id, prefix="利用者"),
            "device_id": str(value.get("device_id") or ""),
            "client_type": client_type(raw_client_type),
            "connection_state": str(value.get("connection_state") or "unknown"),
        }
    return {
        "session_id": str(session_id),
        "last_seen_at": str(value or ""),
        "display_user_id": anonymized_identifier(session_id, prefix="利用者"),
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
            lines.extend(
                [
                    f"[{sanitize_log_line(path.name)}]",
                    *(
                        sanitize_log_line(line)
                        for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[-12:]
                    ),
                ]
            )
        except OSError:
            continue
    return lines[-100:] or ["直近ログはありません"]


def task_rows() -> list[dict[str, str]]:
    try:
        return task_observer.collect_rows()
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


def health_snapshot_note(snapshot: Mapping[str, object], *, now: datetime | None = None) -> str:
    """Return a bounded warning for absent or stale monitor evidence.

    The browser is deliberately read-only: periodic health probing belongs to
    ``SMAI-Host-Monitor``, not to every connected dashboard session.
    """

    checked_at = parse_timestamp(snapshot.get("checked_at"))
    if checked_at is None:
        return "health snapshotの時刻を確認できないため、現在状態を正常と判断できません"
    current = (now or datetime.now(UTC)).astimezone(UTC)
    age = current - checked_at.astimezone(UTC)
    if age > HEALTH_SNAPSHOT_STALE_AFTER:
        return f"health snapshotが{int(age.total_seconds() // 60)}分更新されていません。監視タスクを確認してください"
    return ""


def collect_summary_snapshot() -> dict[str, object]:
    """Read only the compact state required by the periodically refreshed header."""

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
    active_session_count = sum(session_connection_status(session) == "ok" for session in sessions) if activity_available else None

    return {
        "health_note": health_snapshot_note(snapshot),
        "overall": overall,
        "checked_at": snapshot.get("checked_at"),
        "checks": checks,
        "check_statuses": check_statuses,
        "storage": storage,
        "activity_available": activity_available,
        "session_count": len(raw_sessions) if activity_available else None,
        "active_session_count": active_session_count,
        "operation_count": len(raw_operations) if activity_available else None,
        "sessions": sessions,
    }


def collect_operations_snapshot() -> dict[str, object]:
    """Collect bounded detail only when the user opens or explicitly refreshes it."""

    result = collect_summary_snapshot()
    events = read_events()
    try:
        reports = incident_automation.report_rows()
    except (OSError, ValueError, TypeError):
        reports = []
    try:
        notification = incident_automation.notification_status()
    except (OSError, ValueError, TypeError):
        notification = {"status": "unknown", "detail": "通知設定の状態を確認できません"}
    try:
        rollups = telemetry.read_health_rollups(RUNTIME_ROOT, window=timedelta(days=30))
    except (OSError, ValueError, TypeError):
        rollups = []
    connection_history = connection_watch.read(CONNECTION_WATCH_STATE)
    try:
        task_history = task_monitor.read_observations(RUNTIME_ROOT, window=timedelta(days=30))
    except (OSError, ValueError, TypeError):
        task_history = []
    result.update({
        "tasks": task_rows(),
        "events": events,
        "reports": reports,
        "notification": notification,
        "logs": recent_logs(),
        "rollups": rollups,
        "connection_history": connection_history,
        "task_history": task_history,
    })
    return result


if st is not None:

    @st.cache_data(ttl=SNAPSHOT_REFRESH_INTERVAL_SECONDS, show_spinner=False)
    def cached_summary_snapshot() -> dict[str, object]:
        return collect_summary_snapshot()


    @st.cache_data(ttl=DETAIL_SNAPSHOT_TTL_SECONDS, show_spinner=False)
    def cached_operations_snapshot() -> dict[str, object]:
        return collect_operations_snapshot()

else:

    def cached_summary_snapshot() -> dict[str, object]:
        return collect_summary_snapshot()

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
          [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p, [data-testid="stMetricDelta"], [data-testid="stMetricDelta"] * { color: #B9C7D8 !important; opacity: 1 !important; }
          button[kind="secondary"], [data-testid="stButton"] > button { background: #111C2E !important; border-color: #3b587d !important; color: #DCEBFF !important; }
          [data-testid="stButton"] > button:hover { background: #17283F !important; border-color: #60A5FA !important; }
          [data-testid="stButton"] > button:focus-visible { outline: 3px solid rgba(96, 165, 250, 0.65); outline-offset: 2px; }
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
            background: conic-gradient(var(--health-color) var(--score), #253a58 0);
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
          /* The live screen selector is a radio widget so Streamlit does not
             render every hidden surface.  It remains visually and
             operationally equivalent to the previous tab strip. */
          .st-key-operations_view { margin: 8px 0 16px; }
          .st-key-operations_view [role="radiogroup"] { border-bottom: 1px solid #26384f; display: flex; gap: 0; }
          .st-key-operations_view label[data-baseweb="radio"] { align-items: stretch; border-bottom: 2px solid transparent; color: #AAB8C8; cursor: pointer; display: flex; font-weight: 750; margin: 0; min-height: 44px; padding: 0 15px; }
          .st-key-operations_view label[data-baseweb="radio"] > div:first-child { height: 1px; margin: -1px; opacity: 0; overflow: hidden; pointer-events: none; position: absolute; width: 1px; }
          .st-key-operations_view label[data-baseweb="radio"] > div:last-child { align-items: center; display: flex; }
          .st-key-operations_view label[data-baseweb="radio"] p { color: inherit; margin: 0; white-space: nowrap; }
          .st-key-operations_view label[data-baseweb="radio"]:has(input:checked) { border-bottom-color: #22D3EE; color: #22D3EE; }
          .st-key-operations_view label[data-baseweb="radio"]:focus-within { outline: 2px solid #60A5FA; outline-offset: -2px; }
          .responsive-table-wrap { border: 1px solid #26384F; border-radius: 12px; margin: 4px 0 20px; overflow: hidden; }
          .responsive-data-table { border-collapse: collapse; table-layout: fixed; width: 100%; }
          .responsive-data-table th { background: #101C2F; color: #9CC7FF; font-size: 0.73rem; font-weight: 800; letter-spacing: 0.07em; padding: 11px 13px; text-align: left; }
          .responsive-data-table td { border-top: 1px solid #1E3047; color: #DCEBFF; font-size: 0.86rem; line-height: 1.45; overflow-wrap: anywhere; padding: 12px 13px; vertical-align: top; }
          .responsive-data-table tbody tr { background: #0B1423; }
          .responsive-data-table tbody tr:nth-child(even) { background: #0E192B; }
          .responsive-data-table tbody tr:hover { background: #13243B; }
          .responsive-table-status { font-weight: 800; }
          .responsive-table-status-healthy { color: #34D399 !important; }
          .responsive-table-status-degraded { color: #FBBF24 !important; }
          .responsive-table-status-critical { color: #F87171 !important; }
          .responsive-table-status-unknown { color: #AAB8C8 !important; }
          @media (min-width: 2200px) {
            [data-testid="stMainBlockContainer"], .block-container { padding-left: 3rem; padding-right: 3rem; }
            [data-testid="stMetric"] { min-height: 136px; padding: 21px 24px; }
            .topology-node { min-height: 168px; }
          }
          @media (max-width: 767px) {
            .block-container { padding-left: 0.8rem; padding-right: 0.8rem; }
            [data-testid="stMetric"] { min-height: 92px; padding: 12px; }
            .gauge-wrap { align-items: flex-start; flex-direction: column; }
            .topology-node { min-height: 128px; padding: 9px; }
            [data-baseweb="tab"] { font-size: 0.83rem; padding-left: 9px; padding-right: 9px; }
            .responsive-table-wrap { border: 0; border-radius: 0; margin-bottom: 18px; overflow: visible; }
            .responsive-data-table, .responsive-data-table tbody, .responsive-data-table tr, .responsive-data-table td { display: block; width: 100%; }
            .responsive-data-table thead { display: none; }
            .responsive-data-table tbody { display: grid; gap: 10px; }
            .responsive-data-table tbody tr { border: 1px solid #26384F; border-radius: 12px; overflow: hidden; }
            .responsive-data-table tbody tr:nth-child(even), .responsive-data-table tbody tr:hover { background: #0B1423; }
            .responsive-data-table td { align-items: start; border-top: 1px solid #1E3047; display: grid; gap: 10px; grid-template-columns: minmax(86px, 0.72fr) minmax(0, 1.55fr); min-height: 44px; padding: 10px 12px; }
            .responsive-data-table td:first-child { border-top: 0; }
            .responsive-data-table td::before { color: #8FA4BE; content: attr(data-label); font-size: 0.72rem; font-weight: 800; letter-spacing: 0.05em; padding-top: 2px; }
          }

          /* Dense operational shell: cues come from hierarchy and state, not decorative cards. */
          [data-testid="stMainBlockContainer"], .block-container {
            padding-bottom: 1.6rem;
            padding-top: 3.25rem;
          }
          [data-testid="stMetric"] {
            background: transparent;
            border: 0;
            border-left: 1px solid #26384f;
            border-radius: 0;
            min-height: 76px;
            padding: 2px 18px 8px;
          }
          [data-testid="stMetricLabel"] { font-size: 0.78rem; letter-spacing: 0.02em; }
          [data-testid="stMetricValue"] { font-size: 1.8rem; }
          .app-shell {
            align-items: center;
            border-bottom: 1px solid #26384f;
            display: flex;
            justify-content: space-between;
            min-height: 176px;
            padding: 18px 18px 20px;
          }
          .app-brand, .app-state, .app-title, .app-state-copy { align-items: center; display: flex; min-width: 0; }
          .app-brand, .app-state, .app-title { gap: 22px; }
          .app-state-copy { align-items: flex-start; flex-direction: column; gap: 9px; }
          .app-wordmark {
            display: block;
            object-fit: cover;
            height: 86px;
            max-width: min(52vw, 700px);
            width: auto;
          }
          .app-mascot { display: block; height: 132px; margin: -10px 0 -10px -4px; object-fit: contain; width: 132px; }
          .app-name { color: #F8FBFF; font-size: 2rem; letter-spacing: 0.02em; }
          .app-context, .app-state span { color: #8FA4BE; font-size: 0.94rem; letter-spacing: 0.08em; white-space: nowrap; }
          .app-state { border-left: 1px solid #26384f; padding-left: 26px; }
          .app-state .status-pill { font-size: 0.92rem; padding: 6px 13px; }
          .header-control-spacer { height: 57px; }
          [data-testid="stButton"] > button { font-size: 1.02rem; min-height: 50px; }
          [data-baseweb="tab-list"] { border-bottom: 1px solid #26384f; gap: 0; }
          [data-baseweb="tab"] { border-bottom: 2px solid transparent; padding: 11px 15px 9px; }
          [aria-selected="true"][data-baseweb="tab"] { border-bottom-color: #22D3EE; }
          .overview-command {
            align-items: stretch;
            border-bottom: 1px solid #26384f;
            border-top: 1px solid #26384f;
            display: grid;
            gap: 30px;
            grid-template-columns: minmax(0, 1.15fr) minmax(0, 1fr);
            margin: 12px 0 28px;
            padding: 20px 0;
          }
          .overview-state { align-items: center; display: flex; gap: 18px; min-width: 0; }
          .overview-score {
            --health-color: #AAB8C8;
            --score: 0%;
            align-items: center;
            background: conic-gradient(var(--health-color) var(--score), #253a58 0);
            border-radius: 50%;
            color: #F8FBFF;
            display: flex;
            font-size: 1.7rem;
            font-weight: 850;
            height: 94px;
            justify-content: center;
            min-width: 94px;
            position: relative;
          }
          .overview-score::before {
            background: #070D19;
            border-radius: 50%;
            content: "";
            height: 74px;
            position: absolute;
            width: 74px;
          }
          .overview-score span { position: relative; z-index: 1; }
          .overview-score.health-score-healthy, .overview-score.health-score-ok, .overview-score.health-score-active, .overview-score.health-score-running, .overview-score.health-score-ready, .gauge.health-score-healthy, .gauge.health-score-ok, .gauge.health-score-active, .gauge.health-score-running, .gauge.health-score-ready { --health-color: #34D399; --score: 100%; }
          .overview-score.health-score-degraded, .overview-score.health-score-stale, .gauge.health-score-degraded, .gauge.health-score-stale { --health-color: #FBBF24; --score: 62%; }
          .overview-score.health-score-critical, .overview-score.health-score-failed, .overview-score.health-score-error, .gauge.health-score-critical, .gauge.health-score-failed, .gauge.health-score-error { --health-color: #F87171; --score: 18%; }
          .overview-score.health-score-unknown, .gauge.health-score-unknown { --health-color: #AAB8C8; --score: 0%; }
          .overview-state h2 { color: #F8FBFF; font-size: 1.45rem; margin: 0 0 6px; }
          .overview-state p { color: #AAB8C8; margin: 0; }
          .overview-action { border-left: 1px solid #26384f; padding-left: 28px; }
          .overview-destination { color: #22D3EE; font-size: 1.08rem; font-weight: 800; margin: 0 0 7px; }
          .overview-destination span { color: #8FA4BE; padding-left: 4px; }
          .overview-guidance { color: #F8FBFF; font-weight: 700; margin: 0 0 5px; }
          .overview-action small { color: #8FA4BE; }
          .signal-table { border-bottom: 1px solid #26384f; border-top: 1px solid #26384f; margin: 2px 0 20px; }
          .signal-row { align-items: center; border-bottom: 1px solid #1c2b40; display: flex; justify-content: space-between; padding: 13px 4px; }
          .signal-row:last-child { border-bottom: 0; }
          .signal-row div { align-items: baseline; display: flex; gap: 14px; min-width: 0; }
          .signal-row strong { color: #F8FBFF; min-width: 96px; }
          .signal-row span { color: #8FA4BE; font-size: 0.86rem; }
          .detail-handoff { color: #8FA4BE; display: flex; flex-wrap: wrap; gap: 8px 20px; margin-bottom: 8px; }
          .detail-handoff strong { color: #DCEBFF; }
          .detail-handoff b { color: #60A5FA; font-weight: 750; }
          .dashboard-visual-grid { align-items: stretch; display: grid; gap: 22px; grid-template-columns: minmax(0, 1.35fr) minmax(0, 1fr); margin: 4px 0 20px; }
          .visual-surface { border-bottom: 1px solid #26384f; border-top: 1px solid #26384f; min-width: 0; padding: 22px 0 20px; }
          .visual-heading { align-items: baseline; display: flex; justify-content: space-between; margin-bottom: 6px; }
          .visual-heading strong { color: #F8FBFF; font-size: 1rem; }
          .visual-heading span { color: #60A5FA; font-size: 0.7rem; font-weight: 800; letter-spacing: 0.1em; }
          .visual-copy { color: #8FA4BE; font-size: 0.82rem; margin: 0 0 8px; }
          .network-canvas { background: radial-gradient(circle at 50% 13%, rgba(34, 211, 238, 0.11), transparent 54%); height: 528px; overflow: hidden; position: relative; }
          .network-links { height: 100%; inset: 0; overflow: visible; position: absolute; width: 100%; }
          .network-link { fill: none; stroke: #28415e; stroke-dasharray: 7 7; stroke-width: 2; }
          .network-link-flow-halo { fill: none; stroke: #34D399; stroke-linecap: round; stroke-opacity: 0.12; stroke-width: 12; }
          .network-link-active { stroke: #34D399; stroke-dasharray: none; stroke-linecap: round; stroke-opacity: 0.92; stroke-width: 3; }
          .network-packet { filter: drop-shadow(0 0 7px #34D399); }
          .network-packet-return { opacity: 0.72; }
          .network-image-node { align-items: center; display: flex; flex-direction: column; position: absolute; text-align: center; transform: translateX(-50%); width: 190px; z-index: 1; }
          .network-status-healthy, .network-status-ok, .network-status-active, .network-status-running, .network-status-ready { --node-color: #34D399; }
          .network-status-degraded, .network-status-stale { --node-color: #FBBF24; }
          .network-status-critical, .network-status-failed, .network-status-error { --node-color: #F87171; }
          .network-status-idle { --node-color: #758BA6; }
          .network-status-unknown { --node-color: #AAB8C8; }
          .network-topology-image { display: block; filter: drop-shadow(0 10px 14px rgba(0, 0, 0, 0.42)); height: 136px; object-fit: contain; transition: filter 180ms ease; width: 174px; }
          .network-image-node.active .network-topology-image { animation: topology-image-pulse 1.8s ease-out infinite; filter: drop-shadow(0 0 12px var(--node-color)) drop-shadow(0 8px 11px rgba(0, 0, 0, 0.42)); }
          .network-image-label { margin-top: -4px; text-shadow: 0 1px 4px #070D19; }
          .network-image-label b { color: #DCEBFF; display: block; font-size: 0.76rem; letter-spacing: 0.08em; }
          .network-image-label strong { color: #F8FBFF; display: block; font-size: 1rem; margin-top: 3px; }
          .network-image-label span { color: var(--node-color); display: block; font-size: 0.82rem; margin-top: 3px; }
          .network-server { left: 50%; top: 0; }
          .network-server .network-topology-image { height: 152px; width: 182px; }
          .network-server .network-image-label { left: auto; margin: 0; position: absolute; right: calc(100% + 16px); text-align: right; top: 42px; white-space: nowrap; width: 170px; }
          .network-desktop { bottom: 0; left: 16%; }
          .network-desktop .network-topology-image { height: 134px; width: 186px; }
          .network-smartphone { bottom: 0; left: 50%; }
          .network-smartphone .network-topology-image { height: 158px; width: 120px; }
          .network-tablet { bottom: 0; left: 84%; }
          .network-tablet .network-topology-image { height: 134px; width: 186px; }
          .network-legend { color: #758BA6; font-size: 0.73rem; margin: 4px 0 0; }
          .health-score-line { align-items: baseline; display: flex; gap: 8px; margin: 4px 0 2px; }
          .health-score-line strong { color: #F8FBFF; font-size: 1.55rem; }
          .health-score-line span { color: #8FA4BE; font-size: 0.76rem; }
          .health-visual-surface { display: flex; flex-direction: column; gap: 15px; min-height: 674px; }
          .health-history-block, .health-micro-block { display: flex; flex: 1 1 0; flex-direction: column; min-height: 0; }
          .health-history-chart { display: flex; flex: 1 1 0; min-height: 0; }
          .health-history-chart .sparkline, .health-history-chart .chart-unavailable { flex: 1; height: auto; }
          .sparkline { display: block; height: 200px; margin: 10px 0 8px; overflow: visible; width: 100%; }
          .spark-grid { stroke: #1E3047; stroke-dasharray: 3 4; stroke-width: 1; }
          .spark-area { fill-opacity: 0.1; }
          .spark-line { fill: none; stroke-linecap: round; stroke-linejoin: round; stroke-width: 3; }
          .spark-last { stroke: #070D19; stroke-width: 3; }
          .chart-unavailable { align-items: center; border: 1px dashed #31445e; color: #8FA4BE; display: flex; font-size: 0.8rem; height: 150px; justify-content: center; padding: 8px 14px; text-align: center; }
          .micro-trend-grid { border-top: 1px solid #1E3047; display: grid; gap: 18px; grid-template-columns: 1fr 1fr; margin-top: 0; padding-top: 15px; }
          .health-visual-surface .micro-trend-grid { flex: 1 1 0; min-height: 0; }
          .micro-trend { min-width: 0; }
          .health-visual-surface .micro-trend { display: flex; flex-direction: column; }
          .micro-trend header { align-items: baseline; display: flex; justify-content: space-between; }
          .micro-trend header span { color: #8FA4BE; font-size: 0.72rem; }
          .micro-trend header strong { color: #E5EDF7; font-size: 0.86rem; }
          .micro-trend .sparkline { height: 94px; margin: 7px 0 0; }
          .health-visual-surface .micro-trend .sparkline { flex: 1; height: auto; min-height: 0; }
          .micro-trend .chart-unavailable { font-size: 0.7rem; height: 94px; }
          .health-visual-surface .micro-trend .chart-unavailable { flex: 1; height: auto; min-height: 0; }
          .evidence-rail { border-bottom: 1px solid #26384f; border-top: 1px solid #26384f; display: grid; gap: 0; grid-template-columns: repeat(6, minmax(0, 1fr)); margin: 0 0 24px; }
          .evidence-signal { border-left: 1px solid #1E3047; min-height: 72px; padding: 11px 13px; }
          .evidence-signal:first-child { border-left: 0; }
          .evidence-signal small { color: #8FA4BE; display: block; font-size: 0.7rem; letter-spacing: 0.06em; }
          .evidence-signal strong { color: var(--signal-color); display: block; font-size: 0.92rem; margin-top: 5px; }
          .evidence-signal span { color: #B9C7D8; display: block; font-size: 0.72rem; margin-top: 2px; }
          @keyframes topology-image-pulse { 0%, 100% { opacity: 1; transform: translateY(0); } 50% { opacity: 0.95; transform: translateY(-3px); } }
          @media (prefers-reduced-motion: reduce) {
            .network-image-node.active .network-topology-image { animation: none; }
            .network-packet { display: none; }
          }
          /* The same responsive contract as SMAI: phone <= 767px, tablet 768–1024px, desktop >= 1025px. */
          @media (min-width: 768px) and (max-width: 1024px) {
            [data-testid="stMainBlockContainer"], .block-container { padding: 1.25rem 1.25rem 1.75rem; }
            [data-testid="stHorizontalBlock"]:not(:has(.app-shell)) { flex-wrap: wrap; }
            [data-testid="stHorizontalBlock"]:not(:has(.app-shell)) > [data-testid="column"] { flex: 1 1 calc(50% - 0.55rem) !important; min-width: calc(50% - 0.55rem) !important; width: calc(50% - 0.55rem) !important; }
            [data-testid="stHorizontalBlock"]:has(.app-shell) > [data-testid="column"]:first-child { flex: 1 1 calc(100% - 7.75rem) !important; min-width: 0 !important; width: calc(100% - 7.75rem) !important; }
            [data-testid="stHorizontalBlock"]:has(.app-shell) > [data-testid="column"]:last-child { flex: 0 0 7rem !important; min-width: 7rem !important; width: 7rem !important; }
            .app-shell { min-height: 142px; padding: 14px 12px; }
            .app-brand, .app-state, .app-title { gap: 14px; }
            .app-wordmark { height: 68px; max-width: min(46vw, 480px); }
            .app-mascot { height: 100px; margin: -7px -4px -7px 0; width: 100px; }
            .app-state { padding-left: 16px; }
            .network-canvas { height: 468px; }
          }
          @media (min-width: 768px) and (max-width: 900px) {
            [data-testid="stHorizontalBlock"]:has(.visual-surface) > [data-testid="column"] { flex: 1 1 100% !important; min-width: 100% !important; width: 100% !important; }
            /* Preserve the complete product name before secondary context at the narrow tablet breakpoint. */
            .app-context { display: none; }
            .app-wordmark { height: 64px; max-width: min(50vw, 390px); }
            .health-visual-surface { min-height: 560px; }
          }
          @media (max-width: 767px) {
            [data-testid="stMainBlockContainer"], .block-container { padding: 0.9rem 0.85rem calc(1.15rem + env(safe-area-inset-bottom)); }
            [data-testid="stHorizontalBlock"] { flex-wrap: wrap; }
            [data-testid="stHorizontalBlock"] > [data-testid="column"] { flex: 1 1 100% !important; min-width: 100% !important; width: 100% !important; }
            [data-testid="stHorizontalBlock"]:has(> [data-testid="column"] [data-testid="stMetric"]) > [data-testid="column"] { flex: 1 1 calc(50% - 0.38rem) !important; min-width: calc(50% - 0.38rem) !important; width: calc(50% - 0.38rem) !important; }
            [data-testid="stMetric"] { border-left: 0; border-top: 1px solid #26384f; min-height: 80px; padding: 9px 4px 8px; }
            [data-testid="stMetricLabel"] { font-size: 0.72rem; }
            [data-testid="stMetricValue"] { font-size: 1.45rem; }
            [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p { font-size: 0.7rem !important; line-height: 1.35; margin-top: 2px; }
            [data-testid="stHorizontalBlock"]:has(.app-shell) { gap: 8px; }
            .app-shell { align-items: flex-start; flex-direction: column; gap: 8px; min-height: 0; padding: 8px 0 10px; }
            .app-brand { width: 100%; }
            .app-brand, .app-state, .app-title { gap: 10px; }
            .app-state { border-left: 0; padding-left: 0; }
            .app-context { display: none; }
            .app-wordmark { height: 42px; max-width: min(92vw, 430px); }
            .app-mascot { height: 56px; margin: 0; width: 56px; }
            .app-state-copy { gap: 4px; }
            .app-state .status-pill { font-size: 0.78rem; padding: 4px 9px; }
            .app-state span { font-size: 0.76rem; letter-spacing: 0.04em; white-space: normal; }
            .header-control-spacer { display: none; }
            [data-testid="stMarkdownContainer"]:has(.header-control-spacer) + [data-testid="stButton"] button { min-height: 44px; }
            [data-testid="stButton"] > button { font-size: 0.96rem; min-height: 44px; }
            [data-baseweb="tab-list"], [data-testid="stTabs"] [role="tablist"] { flex-wrap: nowrap; overflow-x: auto; overflow-y: hidden; scrollbar-width: thin; }
            [data-baseweb="tab"] { flex: 0 0 auto; font-size: 0.82rem; min-height: 44px; padding: 10px 12px 8px; }
            .st-key-operations_view { margin: 4px 0 14px; }
            .st-key-operations_view [role="radiogroup"] { flex-wrap: nowrap; overflow-x: auto; overflow-y: hidden; scrollbar-width: thin; }
            .st-key-operations_view label[data-baseweb="radio"] { flex: 0 0 auto; font-size: 0.82rem; min-height: 44px; padding: 0 12px; }
            .overview-command { gap: 14px; grid-template-columns: 1fr; margin: 10px 0 18px; padding: 14px 0; }
            .overview-score { font-size: 1.35rem; height: 76px; min-width: 76px; }
            .overview-score::before { height: 60px; width: 60px; }
            .overview-state { gap: 13px; }
            .overview-state h2 { font-size: 1.2rem; }
            .overview-action { border-left: 0; border-top: 1px solid #26384f; padding: 13px 0 0; }
            .signal-row div { align-items: flex-start; flex-direction: column; gap: 3px; }
            .detail-handoff { flex-direction: column; gap: 4px; }
            .visual-surface { padding: 16px 0; }
            .visual-heading { flex-wrap: wrap; gap: 4px 10px; }
            .network-canvas { height: 360px; }
            .health-visual-surface { height: 460px; min-height: 460px; }
            .health-history-block, .health-micro-block { min-height: 0; }
            .network-image-node { width: 112px; }
            .network-server { width: 126px; }
            .network-server .network-topology-image { height: 106px; width: 130px; }
            .network-server .network-image-label { margin-top: -4px; position: static; text-align: center; white-space: normal; width: auto; }
            .network-desktop { left: 17%; }
            .network-desktop .network-topology-image, .network-tablet .network-topology-image { height: 94px; width: 114px; }
            .network-smartphone .network-topology-image { height: 116px; width: 82px; }
            .network-tablet { left: 83%; }
            .evidence-rail { grid-template-columns: repeat(2, minmax(0, 1fr)); }
            .evidence-signal { min-height: 68px; padding: 9px 10px; }
            .evidence-signal:nth-child(odd) { border-left: 0; }
            .evidence-signal:nth-child(n + 3) { border-top: 1px solid #1E3047; }
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


@lru_cache(maxsize=4)
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


@lru_cache(maxsize=8)
def _scaled_transparent_asset(path: str, *, maximum: tuple[int, int]) -> bytes | str | None:
    """Trim transparent margins from a local visual asset at display density."""

    source_path = Path(path)
    if not source_path.is_file():
        return None
    try:
        from PIL import Image

        with Image.open(source_path) as source:
            image = source.convert("RGBA")
            bounds = image.getchannel("A").point(lambda value: 255 if value >= 48 else 0).getbbox()
            if bounds is not None:
                image = image.crop(bounds)
            image.thumbnail(maximum, Image.Resampling.LANCZOS)
            output = BytesIO()
            image.save(output, format="PNG")
            return output.getvalue()
    except (OSError, ValueError, ImportError):
        return str(source_path)


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


def _browser_app_icon() -> bytes | str:
    """Use the Analytics square mark for the browser tab and installed shortcut."""

    try:
        return ANALYTICS_APP_ICON.read_bytes()
    except OSError:
        return "📡"


@lru_cache(maxsize=1)
def _pwa_metadata_component():
    """Serve shortcut metadata from a component so the manifest uses a JSON MIME type."""

    import streamlit.components.v1 as components

    return components.declare_component("smai_pwa_metadata", path=str(PWA_COMPONENT_ROOT))


def _render_web_app_metadata() -> None:
    """Install Apple/PWA metadata without widening the read-only app contract."""

    assert st is not None
    try:
        _pwa_metadata_component()()
    except (ImportError, OSError):
        # The browser tab favicon remains available through set_page_config.
        # Missing optional component support must not block Operations Console.
        return


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


def _dashboard_connection_nodes(data: Mapping[str, object]) -> tuple[bool, list[dict[str, object]]]:
    """Return privacy-safe, current connection facts for the live topology."""

    available = bool(data.get("activity_available"))
    sessions = [item for item in data.get("sessions", []) if isinstance(item, dict)] if isinstance(data.get("sessions"), list) else []
    nodes: list[dict[str, object]] = []
    for client in connection_watch.CLIENT_TYPES:
        typed = [item for item in sessions if str(item.get("client_type") or "") == client]
        active = sum(session_connection_status(item) == "ok" for item in typed)
        status = worst_status(*(session_connection_status(item) for item in typed)) if typed else "idle"
        if not available:
            status = "unknown"
        nodes.append(
            {
                "client": client,
                "label": CLIENT_TYPE_LABELS[client],
                "active": active if available else None,
                "observed": len(typed) if available else None,
                "status": status,
                "flow": available and active > 0,
            }
        )
    return available, nodes


def _dashboard_rollups(data: Mapping[str, object]) -> list[dict[str, object]]:
    return _rollups_for_window(data, "過去24時間")


def _dashboard_health_points(data: Mapping[str, object]) -> list[tuple[datetime, float]]:
    points: list[tuple[datetime, float]] = []
    for row in _dashboard_rollups(data):
        timestamp = parse_timestamp(row.get("bucket_start"))
        if timestamp is None:
            continue
        points.append((timestamp, float(health_score(telemetry.status_from_counts(row.get("overall"))))))
    return points


def _dashboard_latency_points(data: Mapping[str, object]) -> list[tuple[datetime, float]]:
    points: list[tuple[datetime, float]] = []
    for row in _dashboard_rollups(data):
        timestamp = parse_timestamp(row.get("bucket_start"))
        metrics = row.get("latency_ms")
        if timestamp is None or not isinstance(metrics, dict):
            continue
        p95_values = [
            float(metric.get("p95_ms"))
            for metric in metrics.values()
            if isinstance(metric, dict) and isinstance(metric.get("p95_ms"), int) and int(metric["p95_ms"]) >= 0
        ]
        if p95_values:
            points.append((timestamp, max(p95_values)))
    return points


def _dashboard_headroom_points(data: Mapping[str, object]) -> list[tuple[datetime, float]]:
    points: list[tuple[datetime, float]] = []
    for row in _dashboard_rollups(data):
        timestamp = parse_timestamp(row.get("bucket_start"))
        storage = row.get("storage")
        if timestamp is None or not isinstance(storage, list):
            continue
        values = [
            float(item.get("free_percent"))
            for item in storage
            if isinstance(item, dict) and isinstance(item.get("free_percent"), (int, float))
        ]
        if values:
            points.append((timestamp, min(values)))
    return points


def _sparkline_svg(
    points: list[tuple[datetime, float]],
    *,
    color: str,
    label: str,
    lower: float = 0.0,
    upper: float | None = None,
    area: bool = False,
) -> str:
    """Render a bounded inline SVG without inventing missing telemetry."""

    if not points:
        return '<div class="chart-unavailable">履歴なし。欠損を正常の線として描画しません。</div>'
    width, height, padding = 480.0, 200.0, 12.0
    values = [value for _, value in points]
    ceiling = upper if upper is not None else max(max(values) * 1.15, lower + 1.0)
    ceiling = max(ceiling, lower + 1.0)
    count = max(1, len(points) - 1)
    coordinates = [
        (
            padding + (width - padding * 2) * index / count,
            padding + (height - padding * 2) * (1 - min(1.0, max(0.0, (value - lower) / (ceiling - lower)))),
        )
        for index, (_, value) in enumerate(points)
    ]
    polyline = " ".join(f"{x:.1f},{y:.1f}" for x, y in coordinates)
    last_x, last_y = coordinates[-1]
    grid = "".join(
        f'<line class="spark-grid" x1="{padding}" x2="{width - padding}" y1="{y:.1f}" y2="{y:.1f}" />'
        for y in (padding, height / 2, height - padding)
    )
    area_fill = (
        f'<polygon class="spark-area" points="{padding},{height - padding} {polyline} {width - padding},{height - padding}" style="fill:{color}" />'
        if area
        else ""
    )
    return (
        f'<svg class="sparkline" viewBox="0 0 {int(width)} {int(height)}" preserveAspectRatio="none" '
        f'role="img" aria-label="{html.escape(label)}">{area_fill}{grid}'
        f'<polyline class="spark-line" points="{polyline}" style="stroke:{color}" />'
        f'<circle class="spark-last" cx="{last_x:.1f}" cy="{last_y:.1f}" r="5" style="fill:{color}" /></svg>'
    )


def _current_level_statuses(data: Mapping[str, object]) -> dict[str, str]:
    checks = [item for item in data.get("checks", []) if isinstance(item, dict)] if isinstance(data.get("checks"), list) else []
    return {
        level: worst_status(*(str(item.get("status") or "unknown") for item in checks if str(item.get("level") or "").upper() == level))
        if any(str(item.get("level") or "").upper() == level for item in checks)
        else "unknown"
        for level in ("L1", "L2", "L3")
    }


def _render_header(data: Mapping[str, object]) -> None:
    assert st is not None
    app_bar, controls = st.columns((12, 1))
    with app_bar:
        wordmark_asset = ANALYTICS_WORDMARK_LARGE_TEXT if ANALYTICS_WORDMARK_LARGE_TEXT.is_file() else ANALYTICS_WORDMARK
        wordmark = _image_data_uri(_scaled_transparent_asset(str(wordmark_asset), maximum=(700, 180)))
        mascot = _image_data_uri(_scaled_transparent_asset(str(ANALYTICS_MASCOT_HEADER), maximum=(180, 180)))
        brand_mark = f'<img class="app-wordmark" src="{wordmark}" alt="SMAI Analytics">' if wordmark else '<strong class="app-name">SMAI Analytics</strong>'
        mascot_mark = f'<img class="app-mascot" src="{mascot}" alt="SMAI Analytics operations mascot">' if mascot else ""
        st.markdown(
            f'<div class="app-shell"><div class="app-brand"><div class="app-title">{brand_mark}</div><span class="app-context">LOCAL OPERATIONS / READ ONLY</span></div><div class="app-state">{mascot_mark}<div class="app-state-copy">{_status_pill(data["overall"])}<span>最終確認 {html.escape(compact_timestamp(data["checked_at"]))}</span></div></div></div>',
            unsafe_allow_html=True,
        )
    with controls:
        st.markdown('<div class="header-control-spacer header-refresh-anchor"></div>', unsafe_allow_html=True)
        if st.button("更新", key="refresh_now", use_container_width=True):
            cached_summary_snapshot.clear()
            cached_operations_snapshot.clear()
            # A user explicitly requested fresh detail, so this one action may
            # rerun the application. Timed refreshes never take this path.
            st.rerun()


def _render_metrics(data: Mapping[str, object]) -> None:
    assert st is not None
    active_sessions = "—" if data["active_session_count"] is None else str(data["active_session_count"])
    session_detail = "接続情報を取得できません" if data["session_count"] is None else f"観測セッション {data['session_count']}件 / 90秒以内"
    operations = "—" if data["operation_count"] is None else str(data["operation_count"])
    columns = st.columns(4)
    columns[0].metric("ヘルススコア", f"{health_score(data['overall'])} / 100")
    columns[0].caption(status_label(data["overall"]))
    columns[1].metric("現在接続", active_sessions)
    columns[1].caption(session_detail)
    columns[2].metric("実行中の処理", operations)
    columns[2].caption("現在の実行状態")
    columns[3].metric("最終確認", compact_timestamp(data["checked_at"]))
    columns[3].caption(format_timestamp(data["checked_at"]))


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


def _table_status_class(value: object) -> str:
    """Map the displayed Japanese state to a safe visual class."""

    label = str(value or "").strip()
    if label == "正常":
        return "healthy"
    if label in {"要確認", "期限超過"}:
        return "degraded"
    if label in {"重大", "失敗", "エラー"}:
        return "critical"
    return "unknown"


def _render_readonly_table(rows: list[Mapping[str, object]]) -> None:
    """Render read-only evidence as a desktop table and phone-sized evidence cards."""

    assert st is not None
    if not rows:
        return
    columns = list(rows[0].keys())
    headers = "".join(f"<th>{html.escape(str(column))}</th>" for column in columns)
    rendered_rows: list[str] = []
    for row in rows:
        cells: list[str] = []
        for column in columns:
            label = str(column)
            raw_value = row.get(column) if row.get(column) not in (None, "") else "—"
            value = sanitize_log_line(raw_value)
            classes = "responsive-table-value"
            if label in {"状態", "鮮度", "結果", "重要度"}:
                classes += f" responsive-table-status responsive-table-status-{_table_status_class(value)}"
            display_value = html.escape(value).replace("\n", "<br>")
            cells.append(
                f'<td class="{classes}" data-label="{html.escape(label)}">{display_value}</td>'
            )
        rendered_rows.append("<tr>" + "".join(cells) + "</tr>")
    st.markdown(
        '<div class="responsive-table-wrap"><table class="responsive-data-table"><thead><tr>'
        + headers
        + "</tr></thead><tbody>"
        + "".join(rendered_rows)
        + "</tbody></table></div>",
        unsafe_allow_html=True,
    )


def _render_dark_trend_chart(
    rows: list[Mapping[str, object]],
    *,
    x_field: str,
    y_fields: tuple[str, ...],
    height: int,
    y_domain: tuple[float, float] | None = None,
) -> None:
    """Render a compact dark, touch-readable time series without dense x-axis labels."""

    assert st is not None
    try:
        import altair as alt
    except ImportError:  # pragma: no cover - Streamlit installs Altair.
        st.line_chart(rows, x=x_field, y=y_fields, height=height, use_container_width=True)
        return

    points: list[dict[str, object]] = []
    for row in rows:
        timestamp = row.get(x_field)
        if not timestamp:
            continue
        for series in y_fields:
            value = row.get(series)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            points.append({"時刻": timestamp, "系列": series, "値": float(value)})
    if not points:
        st.info("選択期間の時系列値を読み取れません。正常とは判定していません。")
        return

    palette = ("#34D399", "#38BDF8", "#A78BFA", "#F87171", "#FBBF24", "#22D3EE")
    y_scale = alt.Scale(domain=list(y_domain)) if y_domain is not None else alt.Undefined
    chart = (
        alt.Chart(alt.Data(values=points))
        .mark_line(clip=True, strokeWidth=2.6)
        .encode(
            x=alt.X(
                "時刻:T",
                axis=alt.Axis(
                    format="%m/%d %H:%M",
                    grid=False,
                    labelAngle=0,
                    labelColor="#AAB8C8",
                    labelFontSize=11,
                    labelLimit=92,
                    tickColor="#31445E",
                    tickCount=4,
                    title=None,
                ),
            ),
            y=alt.Y(
                "値:Q",
                axis=alt.Axis(
                    grid=True,
                    gridColor="#1E3047",
                    gridOpacity=1,
                    labelColor="#AAB8C8",
                    labelFontSize=11,
                    tickColor="#31445E",
                    tickCount=4,
                    title=None,
                ),
                scale=y_scale,
            ),
            color=alt.Color(
                "系列:N",
                legend=alt.Legend(
                    labelColor="#DCEBFF",
                    labelFontSize=12,
                    orient="bottom",
                    symbolStrokeWidth=4,
                    title=None,
                ),
                scale=alt.Scale(domain=list(y_fields), range=list(palette[: len(y_fields)])),
            ),
            tooltip=(
                alt.Tooltip("時刻:T", format="%Y/%m/%d %H:%M", title="時刻"),
                alt.Tooltip("系列:N", title="系列"),
                alt.Tooltip("値:Q", format=".1f", title="値"),
            ),
        )
        .properties(background="#0B1423", height=height)
        .configure_view(stroke="#26384F", strokeOpacity=1)
        .configure_axis(domainColor="#31445E")
        .configure_legend(padding=12)
    )
    st.altair_chart(chart, use_container_width=True, theme=None)


def _check_attention_summary(data: Mapping[str, object]) -> tuple[str, str] | None:
    """Return a fail-closed visual summary for non-healthy current checks."""
    checks = data.get("checks")
    statuses = [str(item.get("status") or "unknown").casefold() for item in checks if isinstance(item, dict)] if isinstance(checks, list) else []
    failed = sum(STATUS_PRIORITY.get(status, STATUS_PRIORITY["unknown"]) >= STATUS_PRIORITY["failed"] for status in statuses)
    attention = sum(status in {"degraded", "stale"} for status in statuses)
    unknown = sum(status == "unknown" or status not in STATUS_PRIORITY for status in statuses)
    labels = []
    if failed:
        labels.append(f"失敗・重大 {failed}件")
    if attention:
        labels.append(f"要確認・期限超過 {attention}件")
    if unknown:
        labels.append(f"不明 {unknown}件")
    if not labels:
        return None
    level = "error" if failed else "warning"
    return level, f"{' / '.join(labels)}。下の表で対象と詳細を確認してください。"


def _render_gauge(data: Mapping[str, object]) -> None:
    assert st is not None
    score = health_score(data["overall"])
    title, detail = _narrative(str(data["overall"]))
    st.markdown(
        f'<div class="ops-panel gauge-wrap"><div class="gauge {health_gauge_class(data["overall"])}"><span class="gauge-value">{score}</span></div><div class="gauge-copy"><p class="panel-kicker">システム健全性</p><h3>{html.escape(title)}</h3><p>{html.escape(detail)}</p><p style="margin-top:12px">{_status_pill(data["overall"])}</p></div></div>',
        unsafe_allow_html=True,
    )


def health_gauge_class(status: object) -> str:
    normalized = str(status or "unknown").casefold()
    return f"health-score-{normalized}" if normalized in STATUS_COLORS else "health-score-unknown"


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
    return "DashBoard", "直近の監視結果に緊急の要確認項目はありません。", "詳細な推移は推移タブで確認"


def _render_overview_route(tab_name: str, title: str, description: str) -> None:
    assert st is not None
    st.markdown(
        f'<div class="overview-route"><strong>{html.escape(tab_name)}</strong><h3>{html.escape(title)}</h3><p>{html.escape(description)}</p></div>',
        unsafe_allow_html=True,
    )


def _visual_status(status: object) -> tuple[str, str]:
    normalized = str(status or "unknown").casefold()
    if normalized == "idle":
        return "待機", "#758BA6"
    return status_label(normalized), status_color(normalized)


def _network_status_class(status: object) -> str:
    normalized = str(status or "unknown").casefold()
    return f"network-status-{normalized}" if normalized in {*STATUS_COLORS, "idle"} else "network-status-unknown"


def _render_live_connection_map(data: Mapping[str, object]) -> None:
    assert st is not None
    available, nodes = _dashboard_connection_nodes(data)
    overall = str(data.get("overall") or "unknown")
    server_label, _ = _visual_status(overall)
    server_class = " active" if overall.casefold() in {"healthy", "ok", "active", "running"} else ""
    server_status_class = _network_status_class(overall)
    paths = {
        "desktop": "M 500 134 C 436 190 262 276 160 403",
        "smartphone": "M 500 134 C 500 209 500 306 500 401",
        "tablet": "M 500 134 C 564 190 738 276 840 403",
    }
    reverse_paths = {
        "desktop": "M 160 403 C 262 276 436 190 500 134",
        "smartphone": "M 500 401 C 500 306 500 209 500 134",
        "tablet": "M 840 403 C 738 276 564 190 500 134",
    }
    topology_images = {
        "desktop": _topology_tile(0),
        "smartphone": _scaled_transparent_asset(str(TOPOLOGY_SMARTPHONE), maximum=(120, 180)),
        "tablet": _scaled_transparent_asset(str(TOPOLOGY_TABLET), maximum=(180, 130)),
    }
    server_image = _image_data_uri(_topology_tile(2))
    node_markup: list[str] = []
    link_markup: list[str] = []
    packet_markup: list[str] = []
    for index, node in enumerate(nodes):
        client = str(node["client"])
        status_label_text, color = _visual_status(node["status"])
        active = node["active"]
        observed = node["observed"]
        active_text = "観測不能" if active is None else f"現在 {active} 接続"
        observed_text = "" if observed is None or observed == active else f" / 観測 {observed}"
        classes = f"network-image-node network-{client} {_network_status_class(node['status'])}" + (" active" if bool(node["flow"]) else "")
        image_uri = _image_data_uri(topology_images[client])
        image_tag = f'<img class="network-topology-image" src="{image_uri}" alt="{html.escape(CLIENT_TYPE_LABELS[client])}">' if image_uri else ""
        node_markup.append(
            f'<div class="{classes}">{image_tag}<div class="network-image-label">'
            f'<b>{html.escape(CLIENT_TYPE_LABELS[client].upper())}</b><strong>{active_text}</strong>'
            f'<span>{html.escape(status_label_text)}{observed_text}</span></div></div>'
        )
        path = paths[client]
        if bool(node["flow"]):
            link_markup.append(
                f'<path class="network-link-flow-halo" d="{path}" />'
                f'<path class="network-link network-link-active" d="{path}" />'
            )
        else:
            link_markup.append(f'<path class="network-link" d="{path}" />')
        if bool(node["flow"]):
            duration = 2.6 + index * 0.28
            reverse_path = reverse_paths[client]
            packet_markup.extend((
                f'<circle class="network-packet" fill="{color}" r="5">'
                f'<animateMotion dur="{duration:.2f}s" repeatCount="indefinite" path="{path}" /></circle>'
                f'<circle class="network-packet network-packet-return" fill="#E0F2FE" r="4">'
                f'<animateMotion dur="{duration + 0.65:.2f}s" repeatCount="indefinite" path="{reverse_path}" /></circle>',
            ))
    availability_note = (
        "接続情報を読めません。点線を未接続とは判断していません。"
        if not available
        else "実線と往復する粒子は90秒以内にheartbeat通信を観測した接続です。点線は現在の通信を観測していない端末種別です。通信量・内容は表示しません。"
    )
    st.markdown(
        f'<section class="visual-surface"><div class="visual-heading"><strong>ライブ接続トポロジー</strong><span>LIVE HEARTBEAT FLOW</span></div>'
        f'<p class="visual-copy">SMAI Serverと端末種別の現在接続を、個人情報を表示せずに集約します。</p>'
        f'<div class="network-canvas"><svg class="network-links" viewBox="0 0 1000 528" preserveAspectRatio="none" aria-hidden="true">'
        f'{"".join(link_markup)}{"".join(packet_markup)}</svg>'
        f'<div class="network-image-node network-server {server_status_class}{server_class}">'
        f'<img class="network-topology-image" src="{server_image}" alt="SMAI Server"><div class="network-image-label"><b>SERVER</b>'
        f'<strong>SMAI Server</strong><span>{html.escape(server_label)}</span></div></div>{"".join(node_markup)}</div>'
        f'<p class="network-legend">{html.escape(availability_note)}</p></section>',
        unsafe_allow_html=True,
    )


def _render_health_timeline(data: Mapping[str, object]) -> None:
    assert st is not None
    rollups = _dashboard_rollups(data)
    summary = telemetry.window_summary(rollups, window=DASHBOARD_HEALTH_WINDOW)
    health_points = _dashboard_health_points(data)
    latency_points = _dashboard_latency_points(data)
    headroom_points = _dashboard_headroom_points(data)
    score = health_score(data.get("overall"))
    current_color = status_color(data.get("overall"))
    latency_value = "—" if not latency_points else f"{latency_points[-1][1]:.0f} ms"
    headroom_value = "—" if not headroom_points else f"{headroom_points[-1][1]:.1f}%"
    health_chart = _sparkline_svg(health_points, color=current_color, label="過去24時間のHealth score", upper=100.0, area=True)
    latency_chart = _sparkline_svg(latency_points, color="#A78BFA", label="応答p95の推移")
    headroom_chart = _sparkline_svg(headroom_points, color="#34D399", label="空き容量率の推移", upper=100.0)
    st.markdown(
        f'<section class="visual-surface health-visual-surface"><div class="health-history-block"><div class="visual-heading"><strong>Health 24H</strong><span>TIME SERIES</span></div>'
        f'<div class="health-score-line"><strong style="color:{current_color}">{score}</strong>'
        f'<span>履歴カバレッジ {summary["coverage_percent"]}% / {summary["available_buckets"]} 枠</span></div><div class="health-history-chart">{health_chart}</div></div>'
        f'<div class="health-micro-block"><div class="micro-trend-grid"><div class="micro-trend"><header><span>応答 p95</span><strong>{latency_value}</strong></header>{latency_chart}</div>'
        f'<div class="micro-trend"><header><span>最小空き率</span><strong>{headroom_value}</strong></header>{headroom_chart}</div></div></div></section>',
        unsafe_allow_html=True,
    )


def _render_evidence_rail(data: Mapping[str, object]) -> None:
    assert st is not None
    levels = _current_level_statuses(data)
    checks = [item for item in data.get("checks", []) if isinstance(item, dict)] if isinstance(data.get("checks"), list) else []
    latest_latency = max((int(item["latency_ms"]) for item in checks if isinstance(item.get("latency_ms"), int)), default=None)
    storage = [item for item in data.get("storage", []) if isinstance(item, dict)] if isinstance(data.get("storage"), list) else []
    headroom = min((float(item["free_percent"]) for item in storage if isinstance(item.get("free_percent"), (int, float))), default=None)
    tasks = [item for item in data.get("tasks", []) if isinstance(item, dict)] if isinstance(data.get("tasks"), list) else []
    task_status = worst_status(*(str(item.get("status") or "unknown") for item in tasks)) if tasks else "unknown"
    signals: list[tuple[str, str, str, str]] = []
    for level in ("L1", "L2", "L3"):
        label, color = _visual_status(levels[level])
        signals.append((level, label, "現在の検査結果", color))
    signals.extend(
        (
            ("直近応答", "—" if latest_latency is None else f"{latest_latency} ms", "health/pageを含む最大値", "#60A5FA"),
            ("最小空き率", "—" if headroom is None else f"{headroom:.1f}%", "SMAI data / Runtime", "#34D399" if headroom is not None else "#AAB8C8"),
            ("タスク鮮度", status_label(task_status), "Scheduled Task・復元検証", status_color(task_status)),
        )
    )
    rail = "".join(
        f'<div class="evidence-signal" style="--signal-color:{color}"><small>{html.escape(title)}</small><strong>{html.escape(value)}</strong><span>{html.escape(detail)}</span></div>'
        for title, value, detail, color in signals
    )
    st.markdown(f'<div class="evidence-rail">{rail}</div>', unsafe_allow_html=True)


def _render_overview(data: Mapping[str, object]) -> None:
    assert st is not None
    checks = data.get("check_statuses")
    check_statuses = checks if isinstance(checks, dict) else {}
    storage = data.get("storage")
    storage_rows = [item for item in storage if isinstance(item, dict)] if isinstance(storage, list) else []
    storage_status = worst_status(*(str(item.get("status") or "unknown") for item in storage_rows))
    score = health_score(data["overall"])
    title, detail = _narrative(str(data["overall"]))
    destination, guidance, route = _next_check(data)
    st.markdown(
        f'<section class="overview-command"><div class="overview-state"><div class="overview-score {health_gauge_class(data["overall"])}" role="img" aria-label="Health score {score} / 100"><span>{score}</span></div><div><p class="panel-kicker">システム状態</p><h2>{html.escape(title)}</h2><p>{html.escape(detail)}</p></div></div><div class="overview-action"><p class="panel-kicker">次の確認先</p><div class="overview-destination">{html.escape(destination)} <span>→</span></div><p class="overview-guidance">{html.escape(guidance)}</p><small>{html.escape(route)}</small></div></section>',
        unsafe_allow_html=True,
    )

    _panel_heading("現在の監視シグナル", "接続、Health、応答、容量、タスクの根拠を一画面で把握し、詳細は専用タブへ進みます。", kicker="LIVE DASHBOARD")
    network, health = st.columns((7, 5))
    with network:
        _render_live_connection_map(data)
    with health:
        _render_health_timeline(data)
    _render_evidence_rail(data)

    _panel_heading("サービス状態", "現在の3サービスだけを並べます。履歴と個別の根拠は専用タブで確認します。", kicker="LIVE SYSTEMS")
    services = (
        ("SMAI UI", "SMAI本体の画面サービス", service_status(check_statuses, "streamlit")),
        ("Runtime", "ローカル状態・バックアップ", storage_status),
        ("Analytics", "運用コンソール", str(data["overall"])),
    )
    service_rows = "".join(
        f'<div class="signal-row"><div><strong>{html.escape(label)}</strong><span>{html.escape(description)}</span></div>{_status_pill(status)}</div>'
        for label, description, status in services
    )
    st.markdown(f'<div class="signal-table">{service_rows}</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="detail-handoff"><strong>詳細の確認先</strong><span><b>推移</b> 検査・応答・容量</span><span><b>セッション</b> 端末の接続</span><span><b>改善レポート</b> 復元準備</span><span><b>タスク</b> 鮮度・失敗理由</span></div>',
        unsafe_allow_html=True,
    )


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
    attention_summary = _check_attention_summary(data)
    if attention_summary is not None:
        level, message = attention_summary
        getattr(st, level)(message)
    if check_rows:
        _render_readonly_table(check_rows)
    else:
        st.warning("ヘルスチェックの証跡を読み取れません。正常とは判定していません。")

    _panel_heading("HEALTH HISTORY", "overallとL1〜L3の状態スコアを5分集計で表示します。", kicker="TRENDS")
    health_rows: list[dict[str, object]] = []
    for row in rollups:
        timestamp = parse_timestamp(row.get("bucket_start"))
        health_rows.append(
            {
                "時刻": timestamp.astimezone().isoformat() if timestamp is not None else None,
                "overall": health_score(telemetry.status_from_counts(row.get("overall"))),
                "L1": health_score(telemetry.level_status(row, "L1")),
                "L2": health_score(telemetry.level_status(row, "L2")),
                "L3": health_score(telemetry.level_status(row, "L3")),
            }
        )
    if health_rows:
        _render_dark_trend_chart(
            _downsample_rows(health_rows, maximum=96),
            x_field="時刻",
            y_fields=("overall", "L1", "L2", "L3"),
            height=272,
            y_domain=(0, 100),
        )
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
                    "時刻": timestamp.astimezone().isoformat() if timestamp is not None else None,
                    "Streamlit health p95": int(values.get("Streamlit health", {}).get("p95_ms", 0)) if isinstance(values.get("Streamlit health"), dict) else 0,
                    "Streamlit page p95": int(values.get("Streamlit page", {}).get("p95_ms", 0)) if isinstance(values.get("Streamlit page"), dict) else 0,
                }
            )
        if rows:
            _render_dark_trend_chart(
                _downsample_rows(rows, maximum=96),
                x_field="時刻",
                y_fields=("Streamlit health p95", "Streamlit page p95"),
                height=210,
            )
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
                    "時刻": timestamp.astimezone().isoformat() if timestamp is not None else None,
                    "SMAI data": values.get("SMAI data"),
                    "Runtime": values.get("Runtime"),
                }
            )
        if rows:
            _render_dark_trend_chart(
                _downsample_rows(rows, maximum=96),
                x_field="時刻",
                y_fields=("SMAI data", "Runtime"),
                height=210,
                y_domain=(0, 100),
            )
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
                    "観測時刻": observed.astimezone().isoformat() if observed is not None else None,
                    "鮮度スコア": health_score(worst_status(*statuses)),
                    "対象数": len(statuses),
                }
            )
    if task_rows:
        _render_dark_trend_chart(
            task_rows,
            x_field="観測時刻",
            y_fields=("鮮度スコア",),
            height=190,
            y_domain=(0, 100),
        )
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
            rows.append(
                {
                    "利用者": session["display_user_id"],
                    "端末種別": CLIENT_TYPE_LABELS.get(session["client_type"], "種別不明"),
                    "最終通信": f"{relative_time(session['last_seen_at'])} / {format_timestamp(session['last_seen_at'])}",
                    "端末擬似ID": compact_id(session["device_id"]) if session["device_id"] else "—",
                    "状態": status_label(communication),
                }
            )
        st.markdown("#### セッション一覧")
        if rows:
            _render_readonly_table(rows)
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
            "セッション": anonymized_identifier(item.get("session_id"), prefix="セッション"),
        }
        for item in reversed(raw_events)
        if isinstance(item, dict)
    ] if isinstance(raw_events, list) else []
    if event_rows:
        _render_readonly_table(event_rows)
    else:
        st.info("接続観測履歴はまだありません。消失は切断と推測しません。")


def _render_activity_history(data: Mapping[str, object]) -> None:
    assert st is not None
    _panel_heading("操作履歴", "監査イベントを期間・結果・匿名利用者ID・操作名で絞り込みます。", kicker="ACTIVITY HISTORY")
    period, result, user, action = st.columns((2, 2, 3, 3))
    with period:
        selected_window = st.selectbox("期間", tuple(TIME_WINDOW_OPTIONS), key="activity_window")
    with result:
        selected_result = st.selectbox("結果", HISTORY_RESULT_OPTIONS, key="activity_result")
    with user:
        user_query = st.text_input("匿名利用者ID", key="activity_user").strip().casefold()
    with action:
        action_query = st.text_input("操作名", key="activity_action").strip().casefold()
    result_key = filter_key(selected_result)
    events = [item for item in data.get("events", []) if isinstance(item, dict)] if isinstance(data.get("events"), list) else []
    matched = [
        event
        for event in events
        if event_within_window(event.get("timestamp"), selected_window)
        and (result_key == "all" or str(event.get("result") or "").casefold() == result_key)
        and (
            not user_query
            or user_query in anonymized_identifier(event.get("user_id"), prefix="利用者").casefold()
        )
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
            "ユーザー": anonymized_identifier(event.get("user_id"), prefix="利用者"),
            "操作": str(event.get("action") or "—"),
            "対象": str(event.get("target") or "—"),
            "結果": status_label(event.get("result")),
            "端末": anonymized_identifier(event.get("device_id"), prefix="端末"),
            "所要時間": f"{event.get('duration_ms')} ms" if event.get("duration_ms") not in {None, ""} else "—",
        }
        for event in matched
    ]
    if rows:
        _render_readonly_table(rows)
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
        _render_readonly_table(rows)
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
    notification = data.get("notification") if isinstance(data.get("notification"), dict) else {}
    notification_state = str(notification.get("status") or "unknown")
    notification_label = {
        "ready": "設定済み",
        "legacy_ready": "設定済み",
        "unconfigured": "未設定",
        "credential_unavailable": "要確認",
    }.get(notification_state, "不明")
    metrics = st.columns(4)
    metrics[0].metric(
        "復元検証",
        status_label(smoke.get("status")),
        sanitize_log_line(smoke.get("detail") or "記録なし"),
    )
    metrics[1].metric("最小空き率", "—" if headroom is None else f"{headroom:.1f}%", "SMAI data / Runtime")
    metrics[2].metric(
        "履歴カバレッジ",
        f"{summary['coverage_percent']}%",
        f"{summary['available_buckets']} / {summary['expected_buckets']} 枠",
    )
    metrics[3].metric(
        "Gmail通知",
        notification_label,
        f"最終配送: {sanitize_log_line(notification.get('last_delivery') or '記録なし')}",
    )
    with metrics[3]:
        st.caption(sanitize_log_line(notification.get("detail") or "状態を確認できません"))
    st.caption("復元の実行結果と期限はタスク、容量・healthの時系列は推移タブで詳しく確認できます。")

    _panel_heading(
        "改善レポート",
        "重大な障害の調査結果と、固定Gmail通知の安全な配送状態を確認します。",
        kicker="REPORTS",
    )
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
        _render_readonly_table(rows)
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
    _render_readonly_table(rows)


def _render_logs(data: Mapping[str, object]) -> None:
    assert st is not None
    _panel_heading("ログ一覧", "直近の監視・運用ログを最大100行まで表示します。", kicker="LOGS")
    lines = [sanitize_log_line(item) for item in data.get("logs", [])] if isinstance(data.get("logs"), list) else []
    errors = sum(any(token in line.casefold() for token in ("error", "failed", "critical")) for line in lines)
    warnings = sum("warn" in line.casefold() for line in lines)
    sources = sum(1 for line in lines if line.startswith("["))
    metrics = st.columns(3)
    metrics[0].metric("表示行", str(len(lines)), "直近ログの抜粋")
    metrics[1].metric("警告", str(warnings), "warn を含む行")
    metrics[2].metric("異常語", str(errors), f"ログソース {sources}件")
    limit = st.selectbox("表示行数", (25, 50, 100), index=2, key="log_limit")
    st.code("\n".join(lines[-limit:]) if lines else "ログを読み取れません", language="text")


def _render_live_header() -> None:
    """Refresh only the compact header summary on the periodic timer."""

    assert st is not None
    data = cached_summary_snapshot()
    _render_header(data)
    _render_metrics(data)
    if data["health_note"]:
        st.warning(str(data["health_note"]))
    st.caption(
        f"サマリーは{SUMMARY_REFRESH_INTERVAL_SECONDS}秒ごとに部分更新 / 詳細は画面切替または更新操作で最新化 / 最終表示 "
        f"{datetime.now().astimezone().strftime('%H:%M:%S')} / この画面は閲覧専用です"
    )


if st is not None:

    @st.fragment(run_every=SUMMARY_REFRESH_INTERVAL_SECONDS)
    def _live_header_fragment() -> None:
        _render_live_header()

else:
    # Keep pure helper tests importable when the optional Web runtime is absent.
    _live_header_fragment = _render_live_header


def render_dashboard() -> None:
    """Render static detail once; only the header fragment has a timed rerun."""

    assert st is not None
    _live_header_fragment()
    selected_view = st.radio(
        "表示画面",
        WEB_TAB_LABELS,
        horizontal=True,
        label_visibility="collapsed",
        key="operations_view",
    )
    data = cached_operations_snapshot()
    if selected_view == "DashBoard":
        _render_overview(data)
    elif selected_view == "推移":
        _render_trends(data)
    elif selected_view == "セッション":
        _render_connections(data)
    elif selected_view == "操作履歴":
        _render_activity_history(data)
    elif selected_view == "障害":
        _render_incidents(data)
    elif selected_view == "改善レポート":
        _render_reports(data)
    elif selected_view == "タスク":
        _render_tasks(data)
    elif selected_view == "ログ":
        _render_logs(data)


def main() -> None:
    if st is None:
        raise RuntimeError("Streamlit is required. Run this app with the SMAI Analytics virtual environment.")
    st.set_page_config(page_title="SMAI Analytics | Operations Console", page_icon=_browser_app_icon(), layout="wide", initial_sidebar_state="collapsed")
    _render_web_app_metadata()
    _render_styles()
    render_dashboard()


if __name__ == "__main__":
    main()
