"""Read-only SMAI Analytics dashboard for trusted private networks.

This Streamlit surface deliberately owns no SMAI calculation, ranking, or
user-facing application state.  It reads the same stable files as the local
Tkinter console and runs the server-local health probe at a bounded interval.
The launcher binds it to a separate port so it never competes with SMAI's
primary Streamlit application.
"""

from __future__ import annotations

import html
import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Mapping

import incident_automation
import task_monitor
import telemetry

try:  # Keep pure helper tests usable with the lightweight Tkinter environment.
    import streamlit as st
except ImportError:  # pragma: no cover - the web launcher requires Streamlit
    st = None


PROJECT_ROOT = Path(os.environ.get("SMAI_PROJECT_ROOT", r"C:\Users\user\workspace\SMAI_Projects\Smart_Market_AI"))
RUNTIME_ROOT = Path(os.environ.get("SMAI_RUNTIME_ROOT", r"C:\Users\user\workspace\SMAI_Projects\SMAI_Server_Runtime"))
SNAPSHOT = PROJECT_ROOT / "data/ops/server_ops/health_snapshot.json"
ACTIVITY = PROJECT_ROOT / "data/ops/server_ops/activity_state.json"
EVENT_LOG = RUNTIME_ROOT / "audit/events.jsonl"
BACKUP_SMOKE_STATE = RUNTIME_ROOT / "backup_restore_smoke.json"
CONNECTION_WATCH_STATE = RUNTIME_ROOT / "connections/watch_state.json"
LOG_ROOTS = (RUNTIME_ROOT / "logs", PROJECT_ROOT / "logs/server_ops", PROJECT_ROOT / "logs/maintenance")
ASSET_ROOT = Path(__file__).with_name("assets")
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


def expected_task_root(task: str) -> Path:
    return Path(__file__).resolve().parent if task in {"SMAI-Server-Analytics", "SMAI-Incident-Automation"} else PROJECT_ROOT


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

    try:
        result = subprocess.run(
            [sys.executable, str(Path(__file__).with_name("health.py"))],
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
        rollups = telemetry.read_health_rollups(RUNTIME_ROOT, window=timedelta(hours=24))
    except (OSError, ValueError, TypeError):
        rollups = []
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
          [data-testid="stHeader"] { background: rgba(7, 13, 25, 0.92); }
          [data-testid="stMetric"] {
            background: #111F35;
            border: 1px solid #354763;
            border-radius: 12px;
            padding: 16px 18px;
            min-height: 116px;
          }
          [data-testid="stMetricLabel"] { color: #AAB8C8; font-weight: 700; }
          [data-testid="stMetricValue"] { color: #F8FBFF; }
          .status-card {
            background: #111F35;
            border: 1px solid #354763;
            border-radius: 12px;
            padding: 16px 18px;
            min-height: 110px;
          }
          .status-card h2 { color: #F8FBFF; font-size: 1.15rem; margin: 10px 0 6px; }
          .status-card p { color: #AAB8C8; margin: 0; }
          .status-pill {
            border: 1px solid;
            border-radius: 999px;
            display: inline-block;
            font-size: 0.78rem;
            font-weight: 800;
            letter-spacing: 0.06em;
            padding: 4px 10px;
          }
          .topology-node {
            background: #111F35;
            border: 1px solid #354763;
            border-radius: 12px;
            min-height: 156px;
            padding: 12px;
            text-align: center;
          }
          .topology-node strong { color: #F8FBFF; display: block; margin-top: 4px; }
          .topology-node small { color: #AAB8C8; }
          .section-note { color: #AAB8C8; font-size: 0.9rem; }
          @media (min-width: 2200px) {
            .block-container { max-width: 2200px; padding-left: 3.2rem; padding-right: 3.2rem; }
            [data-testid="stMetric"] { min-height: 142px; padding: 22px 24px; }
          }
          @media (max-width: 760px) {
            .block-container { padding-left: 0.8rem; padding-right: 0.8rem; }
            [data-testid="stMetric"] { min-height: 94px; padding: 12px; }
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_header(data: Mapping[str, object]) -> None:
    assert st is not None
    brand, status = st.columns((7, 3))
    with brand:
        if ANALYTICS_WORDMARK.is_file():
            st.image(str(ANALYTICS_WORDMARK), width=440)
        else:
            st.title("SMAI Analytics")
        st.caption("Operations Console  /  常時ローカル監視  /  信頼済みプライベートLAN閲覧")
    with status:
        if ANALYTICS_MASCOT.is_file():
            mascot, details = st.columns((1, 2))
            with mascot:
                st.image(str(ANALYTICS_MASCOT), width=78)
            with details:
                title, detail = _narrative(str(data["overall"]))
                st.markdown(f'<div class="status-card">{_status_pill(data["overall"])}<h2>{html.escape(title)}</h2><p>{html.escape(detail)}</p></div>', unsafe_allow_html=True)
        else:
            title, detail = _narrative(str(data["overall"]))
            st.markdown(f'<div class="status-card">{_status_pill(data["overall"])}<h2>{html.escape(title)}</h2><p>{html.escape(detail)}</p></div>', unsafe_allow_html=True)


def _render_metrics(data: Mapping[str, object]) -> None:
    assert st is not None
    score = health_score(data["overall"])
    sessions = "—" if data["session_count"] is None else str(data["session_count"])
    operations = "—" if data["operation_count"] is None else str(data["operation_count"])
    columns = st.columns(4)
    columns[0].metric("Health score", f"{score} / 100", status_label(data["overall"]))
    columns[1].metric("接続セッション", sessions, "activity state")
    columns[2].metric("実行中の処理", operations, "現在の処理数")
    columns[3].metric("最終確認", compact_timestamp(data["checked_at"]), format_timestamp(data["checked_at"]))


def _render_topology_node(column: object, *, label: str, detail: str, status: str, image_path: Path | None = None) -> None:
    assert st is not None
    with column:
        if image_path is not None and image_path.is_file():
            st.image(str(image_path), width=64)
        st.markdown(
            f'<div class="topology-node"><strong>{html.escape(label)}</strong><small>{html.escape(detail)}</small><br><br>{_status_pill(status)}</div>',
            unsafe_allow_html=True,
        )


def _render_overview(data: Mapping[str, object]) -> None:
    assert st is not None
    topology, history = st.columns((6, 7))
    checks = data["check_statuses"]
    if not isinstance(checks, dict):
        checks = {}
    sessions = data["sessions"]
    session_rows = sessions if isinstance(sessions, list) else []
    client_statuses = {
        client: worst_status(*(session_connection_status(item) for item in session_rows if item.get("client_type") == client))
        if any(item.get("client_type") == client for item in session_rows)
        else "unknown"
        for client in ("desktop", "smartphone", "tablet")
    }
    storage_status = worst_status(*(str(item.get("status") or "unknown") for item in data["storage"] if isinstance(item, dict)))
    with topology:
        st.subheader("SERVICE TOPOLOGY")
        st.caption("端末の状態は、SMAIが受信したheartbeatの鮮度だけを根拠に表示します。")
        clients = st.columns(3)
        _render_topology_node(clients[0], label="SMAI UI", detail="PC browser", status=client_statuses["desktop"], image_path=ANALYTICS_LOGO)
        _render_topology_node(clients[1], label="スマートフォン", detail="mobile browser", status=client_statuses["smartphone"], image_path=TOPOLOGY_SMARTPHONE)
        _render_topology_node(clients[2], label="タブレット", detail="tablet browser", status=client_statuses["tablet"], image_path=TOPOLOGY_TABLET)
        st.markdown("<p class='section-note' style='text-align:center'>↓ 同じ信頼済みネットワーク内のWeb App ↓</p>", unsafe_allow_html=True)
        services = st.columns(3)
        _render_topology_node(services[0], label="Streamlit", detail="SMAI Web App", status=service_status(checks, "streamlit"), image_path=TOPOLOGY_SPRITE)
        _render_topology_node(services[1], label="Runtime", detail="local state / backup", status=storage_status)
        _render_topology_node(services[2], label="Analytics", detail="ops observations", status=str(data["overall"]), image_path=ANALYTICS_LOGO)
    with history:
        st.subheader("HEALTH TIMELINE")
        st.caption("5分単位の永続履歴。欠損は正常として扱いません。")
        rollups = data["rollups"]
        chart_rows: list[dict[str, object]] = []
        if isinstance(rollups, list):
            for row in rollups:
                if not isinstance(row, dict):
                    continue
                timestamp = parse_timestamp(row.get("bucket_start"))
                chart_rows.append(
                    {
                        "時刻": timestamp.astimezone().strftime("%H:%M") if timestamp is not None else "時刻不明",
                        "Health score": health_score(telemetry.status_from_counts(row.get("overall"))),
                    }
                )
        if chart_rows:
            st.line_chart(chart_rows, x="時刻", y="Health score", height=280, use_container_width=True)
        else:
            st.info("永続ヘルス履歴はまだありません。最初の5分集計後に表示されます。")

    st.subheader("CHECK MATRIX")
    check_rows = [
        {
            "レベル": str(item.get("level") or "—"),
            "チェック": str(item.get("name") or "—"),
            "状態": status_label(item.get("status")),
            "詳細": str(item.get("detail") or item.get("message") or "—"),
            "応答": f"{item.get('latency_ms')} ms" if isinstance(item.get("latency_ms"), int) else "—",
        }
        for item in data["checks"]
        if isinstance(item, dict)
    ]
    if check_rows:
        st.dataframe(check_rows, use_container_width=True, hide_index=True)
    else:
        st.warning("ヘルスチェックの証跡を読み取れません。正常とは判定していません。")

    st.subheader("RECOVERY READINESS")
    storage = data["storage"]
    storage_rows = [
        {
            "対象": str(item.get("name") or "—"),
            "状態": status_label(item.get("status")),
            "空き容量": format_bytes(item.get("free_bytes")),
            "空き率": f"{item.get('free_percent')}%" if item.get("free_percent") is not None else "—",
        }
        for item in storage
        if isinstance(item, dict)
    ]
    if storage_rows:
        st.dataframe(storage_rows, use_container_width=True, hide_index=True)
    else:
        st.info("保存容量の観測値はまだありません。")


def _render_connections(data: Mapping[str, object]) -> None:
    assert st is not None
    st.subheader("端末接続状況")
    if not bool(data["activity_available"]):
        st.warning("activity state を読み取れません。接続がない、とは判断していません。")
        return
    sessions = data["sessions"]
    rows = []
    for session in sessions if isinstance(sessions, list) else []:
        if not isinstance(session, dict):
            continue
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
    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.info("接続中のセッションはありません。")


def _render_tasks(data: Mapping[str, object]) -> None:
    assert st is not None
    st.subheader("タスク鮮度")
    rows = [
        {
            "タスク": str(row.get("name") or "—"),
            "鮮度": status_label(row.get("status")),
            "最終実行": format_timestamp(row.get("last_run_at")),
            "次回予定": str(row.get("next_run_at") or "—"),
            "最終結果": str(row.get("last_result") or "—"),
            "判定理由": str(row.get("detail") or "—"),
        }
        for row in data["tasks"]
        if isinstance(row, dict)
    ]
    st.dataframe(rows, use_container_width=True, hide_index=True)


def _render_incidents(data: Mapping[str, object]) -> None:
    assert st is not None
    st.subheader("障害と改善レポート")
    events = [
        event
        for event in data["events"]
        if isinstance(event, dict) and str(event.get("result") or "").casefold() in {"failed", "error", "critical"}
    ]
    incident_rows = [
        {
            "時刻": format_timestamp(event.get("timestamp")),
            "操作": str(event.get("action") or "—"),
            "対象": str(event.get("target") or "—"),
            "結果": status_label(event.get("result")),
        }
        for event in events
    ]
    if incident_rows:
        st.dataframe(incident_rows, use_container_width=True, hide_index=True)
    else:
        st.success("現在の監査イベントに failed / error / critical はありません。")
    reports = [
        {
            "記録時刻": format_timestamp(report.get("reported_at")),
            "調査依頼": compact_id(report.get("request_id"), limit=28),
            "重要度": str(report.get("severity") or "—").upper(),
            "状態": status_label(report.get("status")),
            "改善結果": str(report.get("summary") or "調査結果はまだ記録されていません。"),
        }
        for report in data["reports"]
        if isinstance(report, dict)
    ]
    if reports:
        st.markdown("#### 改善レポート")
        st.dataframe(reports, use_container_width=True, hide_index=True)


def _render_logs(data: Mapping[str, object]) -> None:
    assert st is not None
    st.subheader("直近ログ")
    lines = data["logs"]
    st.code("\n".join(str(line) for line in lines) if isinstance(lines, list) else "ログを読み取れません", language="text")


def render_dashboard() -> None:
    assert st is not None
    data = cached_operations_snapshot()
    _render_header(data)
    _render_metrics(data)
    if data["health_note"]:
        st.warning(str(data["health_note"]))
    overview, connections, tasks, incidents, logs = st.tabs(("概要", "接続", "タスク", "障害", "ログ"))
    with overview:
        _render_overview(data)
    with connections:
        _render_connections(data)
    with tasks:
        _render_tasks(data)
    with incidents:
        _render_incidents(data)
    with logs:
        _render_logs(data)
    st.caption(f"5秒ごとに更新 / 最終表示 {datetime.now().astimezone().strftime('%H:%M:%S')} / この画面は閲覧専用です")


def main() -> None:
    if st is None:
        raise RuntimeError("Streamlit is required. Run this app with the SMAI virtual environment.")
    st.set_page_config(page_title="SMAI Analytics | Operations Console", page_icon="📡", layout="wide", initial_sidebar_state="collapsed")
    _render_styles()

    @st.fragment(run_every=5)
    def live_dashboard() -> None:
        render_dashboard()

    live_dashboard()


if __name__ == "__main__":
    main()
