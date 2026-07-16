"""Fail-closed incident handoff, report retention, and administrator mail outbox.

Analytics never imports SMAI private modules or changes SMAI source code.  A
critical health condition becomes a durable, deduplicated Codex investigation
request in the local Runtime directory.  A separate Codex or operator process
can then investigate and register its outcome with the ``report`` command.
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import html
import json
import os
import re
import smtplib
import ssl
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from pathlib import Path
from typing import Iterable, Mapping

from ..monitoring import health
from . import admin_settings, codex_autofix, windows_credentials

RUNTIME_ROOT = Path(
    os.environ.get(
        "SMAI_RUNTIME_ROOT",
        r"C:\Users\user\workspace\SMAI_Projects\SMAI_Server_Runtime",
    )
)
INCIDENT_ROOT = RUNTIME_ROOT / "incident_operations"
REQUESTS_DIR = INCIDENT_ROOT / "codex_requests"
REPORTS_DIR = INCIDENT_ROOT / "reports"
OUTBOX_DIR = INCIDENT_ROOT / "admin_outbox"
STATE_PATH = INCIDENT_ROOT / "state.json"
REQUEST_INDEX_PATH = INCIDENT_ROOT / "codex_requests.jsonl"
REPORT_INDEX_PATH = INCIDENT_ROOT / "improvement_reports.jsonl"
OUTBOX_INDEX_PATH = INCIDENT_ROOT / "admin_notifications.jsonl"
GMAIL_CONFIG_PATH = INCIDENT_ROOT / "gmail_notification.json"
APPROVALS_DIR = INCIDENT_ROOT / "codex_approvals"
DEDUPLICATION_WINDOW = timedelta(minutes=30)
RENOTIFICATION_WINDOW = timedelta(minutes=15)
DELIVERY_RETRY_LIMIT = 3
DELIVERY_RETRY_DELAYS = (timedelta(minutes=5), timedelta(minutes=15), timedelta(minutes=30))
GMAIL_SMTP_HOST = "smtp.gmail.com"
GMAIL_SMTP_PORT = 587
GMAIL_CREDENTIAL_TARGET = "SMAI-Analytics-Gmail-SMTP"
ASSET_ROOT = Path(__file__).resolve().parents[2] / "assets"
EMAIL_BRAND_IMAGE = ASSET_ROOT / "smai-analytics-wordmark-header.png"
EMAIL_REPAIR_IMAGE = ASSET_ROOT / "smai-analytics-incident-repair-v1.png"
SCHEMA_VERSION = 2


def utc_now() -> datetime:
    return datetime.now(UTC)


def _timestamp(value: datetime | None = None) -> str:
    return (value or utc_now()).isoformat()


def _safe_text(value: object, *, limit: int = 240) -> str:
    return str(value).replace("\r", " ").replace("\n", " ").strip()[:limit]


def _safe_request_id(value: object) -> str:
    candidate = _safe_text(value, limit=120)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,119}", candidate):
        raise ValueError("request_id is invalid")
    return candidate


def _load_json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


def _load_jsonl(path: Path) -> list[dict[str, object]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    rows: list[dict[str, object]] = []
    for line in lines:
        try:
            value = json.loads(line)
        except (TypeError, ValueError):
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def _write_json_atomic(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _append_jsonl(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")


def _valid_email(value: object) -> str:
    """Accept one bounded mailbox address without retaining display names."""

    candidate = str(value or "").strip()
    local, separator, domain = candidate.partition("@")
    if (
        not separator
        or not local
        or not domain
        or len(candidate) > 254
        or any(character.isspace() for character in candidate)
        or "." not in domain
    ):
        raise ValueError("A single valid email address is required.")
    return candidate


def _normalized_gmail_app_password(value: object) -> str:
    """Accept Google's visually grouped app password without persisting its spaces."""

    return "".join(str(value or "").split())


def _read_gmail_secret(target: str) -> tuple[str, str] | None:
    """Read the app password only at delivery time; callers must not log it."""

    return windows_credentials.read_generic_secret(target=target)


def configure_fixed_gmail(*, sender: str, recipient: str, app_password: str) -> dict[str, object]:
    """Persist one local Gmail recipient and protect its app password in Windows."""

    normalized_sender = _valid_email(sender)
    normalized_recipient = _valid_email(recipient)
    normalized_password = _normalized_gmail_app_password(app_password)
    if not normalized_password:
        raise ValueError("A Gmail app password is required.")
    windows_credentials.write_generic_secret(
        target=GMAIL_CREDENTIAL_TARGET,
        username=normalized_sender,
        secret=normalized_password,
    )
    _write_json_atomic(
        GMAIL_CONFIG_PATH,
        {
            "schema_version": SCHEMA_VERSION,
            "provider": "gmail_smtp",
            "sender": normalized_sender,
            "recipient": normalized_recipient,
            "host": GMAIL_SMTP_HOST,
            "port": GMAIL_SMTP_PORT,
            "credential_target": GMAIL_CREDENTIAL_TARGET,
            "configured_at": _timestamp(),
        },
    )
    return notification_status()


def _gmail_delivery_configuration() -> dict[str, object] | None:
    config = _load_json(GMAIL_CONFIG_PATH)
    if config.get("provider") != "gmail_smtp":
        return None
    try:
        sender = _valid_email(config.get("sender"))
        recipient = _valid_email(config.get("recipient"))
        port = int(config.get("port") or GMAIL_SMTP_PORT)
    except (TypeError, ValueError):
        return None
    target = str(config.get("credential_target") or GMAIL_CREDENTIAL_TARGET).strip()
    if not target or port != GMAIL_SMTP_PORT or str(config.get("host") or "").strip() != GMAIL_SMTP_HOST:
        return None
    credential = _read_gmail_secret(target)
    if credential is None:
        return None
    username, password = credential
    password = _normalized_gmail_app_password(password)
    if not password:
        return None
    return {
        "provider": "gmail_smtp",
        "recipient": recipient,
        "sender": sender,
        "host": GMAIL_SMTP_HOST,
        "port": GMAIL_SMTP_PORT,
        "username": username or sender,
        "password": password,
    }


def _legacy_smtp_delivery_configuration() -> dict[str, object] | None:
    """Keep an existing explicit SMTP deployment usable during Gmail migration."""

    recipient = os.environ.get("SMAI_ADMIN_EMAIL_TO", "").strip()
    sender = os.environ.get("SMAI_ADMIN_EMAIL_FROM", "").strip()
    host = os.environ.get("SMAI_ADMIN_SMTP_HOST", "").strip()
    if not recipient or not sender or not host:
        return None
    try:
        return {
            "provider": "legacy_smtp",
            "recipient": _valid_email(recipient),
            "sender": _valid_email(sender),
            "host": host,
            "port": int(os.environ.get("SMAI_ADMIN_SMTP_PORT", "587")),
            "username": os.environ.get("SMAI_ADMIN_SMTP_USERNAME", "").strip(),
            "password": os.environ.get("SMAI_ADMIN_SMTP_PASSWORD", ""),
        }
    except ValueError:
        return None


def _delivery_configuration() -> dict[str, object] | None:
    """Prefer the protected fixed Gmail setup; legacy SMTP remains opt-in only."""

    try:
        gmail = _gmail_delivery_configuration()
    except windows_credentials.CredentialManagerError:
        gmail = None
    return gmail or _legacy_smtp_delivery_configuration()


def _last_notification_result() -> tuple[str, str]:
    rows = _load_jsonl(OUTBOX_INDEX_PATH)
    if not rows:
        return "記録なし", ""
    latest = rows[-1]
    return _safe_text(latest.get("status") or "不明", limit=40), _safe_text(latest.get("delivered_at") or latest.get("created_at"), limit=80)


def notification_status() -> dict[str, object]:
    """Return a secret-free, read-only notification state for the Operations UI."""

    config = _load_json(GMAIL_CONFIG_PATH)
    last_status, last_at = _last_notification_result()
    if config.get("provider") == "gmail_smtp":
        try:
            sender = _valid_email(config.get("sender"))
            recipient = _valid_email(config.get("recipient"))
            credential = _read_gmail_secret(str(config.get("credential_target") or GMAIL_CREDENTIAL_TARGET))
        except (ValueError, windows_credentials.CredentialManagerError):
            credential = None
            sender = ""
            recipient = ""
        if sender and recipient and credential and credential[1]:
            return {
                "status": "ready",
                "provider": "Gmail SMTP",
                "detail": "固定宛先・Credential Manager設定済み",
                "last_delivery": last_status,
                "last_delivery_at": last_at,
            }
        return {
            "status": "credential_unavailable",
            "provider": "Gmail SMTP",
            "detail": "Gmail設定はあるが、このWindowsユーザーのCredential Managerを読めません",
            "last_delivery": last_status,
            "last_delivery_at": last_at,
        }
    if _legacy_smtp_delivery_configuration():
        return {
            "status": "legacy_ready",
            "provider": "SMTP",
            "detail": "既存の明示SMTP設定を使用中",
            "last_delivery": last_status,
            "last_delivery_at": last_at,
        }
    return {
        "status": "unconfigured",
        "provider": "未設定",
        "detail": "外部メールは送信せず、ローカルoutboxへ記録します",
        "last_delivery": last_status,
        "last_delivery_at": last_at,
    }


def _fingerprint(kind: str, evidence: Iterable[str]) -> str:
    normalized = "|".join([kind, *sorted(_safe_text(item, limit=120) for item in evidence)])
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]
    return f"{kind}-{digest}"


def critical_health_incident(snapshot: Mapping[str, object]) -> dict[str, object] | None:
    """Return an actionable incident only for a fail-closed critical state."""

    if str(snapshot.get("overall", "")).lower() != "critical":
        return None
    checks = snapshot.get("checks")
    check_rows = checks if isinstance(checks, list) else []
    failed_checks = [
        _safe_text(item.get("name"))
        for item in check_rows
        if isinstance(item, dict)
        if str(item.get("status", "")).lower() == "failed"
    ]
    evidence = failed_checks or ["critical health without readable checks"]
    return {
        "severity": "critical",
        "source": "health",
        "fingerprint": _fingerprint("critical-health", evidence),
        "title": "SMAI critical health alert",
        "evidence": evidence,
        "checked_at": _safe_text(snapshot.get("checked_at")),
    }


def _request_id(fingerprint: str, now: datetime) -> str:
    return f"incident-{now.strftime('%Y%m%dT%H%M%SZ')}-{fingerprint.rsplit('-', 1)[-1]}"


def _request_markdown(request: Mapping[str, object]) -> str:
    evidence = request.get("evidence")
    lines = [
        f"# Codex investigation request: {request['request_id']}",
        "",
        f"- Severity: `{request['severity']}`",
        f"- Source: `{request['source']}`",
        f"- Fingerprint: `{request['fingerprint']}`",
        f"- Requested at (UTC): {request['requested_at']}",
        "",
        "## Evidence",
        "",
    ]
    lines.extend(f"- {_safe_text(item)}" for item in evidence if isinstance(evidence, list))
    lines.extend(
        [
            "",
            "## Required investigation",
            "",
            "1. This is a local draft. Do not begin a Codex repair task until a matching administrator approval exists.",
            "2. Confirm the alert with SMAI health, audit, and relevant runtime logs.",
            "3. Identify the root cause without changing investment calculations automatically.",
            "4. Apply the smallest safe fix only when the failure is reproducible and in scope.",
            "5. Run targeted deterministic checks and inspect the local Analytics screen before recording an improvement report.",
            "6. Do not expose credentials, user content, prompt text, or raw provider responses.",
        ]
    )
    return "\n".join(lines) + "\n"


def _deduplication_allowed(state: Mapping[str, object], fingerprint: str, now: datetime) -> bool:
    open_incidents = state.get("open_incidents")
    if not isinstance(open_incidents, dict):
        return True
    previous = open_incidents.get(fingerprint)
    if not isinstance(previous, dict):
        return True
    previous_at = _parse_timestamp(previous.get("last_requested_at"))
    return previous_at is None or now - previous_at >= DEDUPLICATION_WINDOW


def _parse_timestamp(value: object) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def create_codex_request(incident: Mapping[str, object], *, now: datetime | None = None) -> dict[str, object] | None:
    """Persist one deduplicated local investigation request and initial report."""

    current = now or utc_now()
    fingerprint = _safe_text(incident.get("fingerprint"), limit=100)
    if not fingerprint:
        return None
    state = _load_json(STATE_PATH)
    if not _deduplication_allowed(state, fingerprint, current):
        return None
    request_id = _request_id(fingerprint, current)
    request: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "request_id": request_id,
        "severity": _safe_text(incident.get("severity") or "critical", limit=20),
        "source": _safe_text(incident.get("source") or "health", limit=40),
        "fingerprint": fingerprint,
        "title": _safe_text(incident.get("title") or "SMAI incident", limit=160),
        "evidence": [_safe_text(item) for item in incident.get("evidence", []) if _safe_text(item)],
        "checked_at": _safe_text(incident.get("checked_at")),
        "requested_at": _timestamp(current),
        "status": "pending_investigation",
    }
    REQUESTS_DIR.mkdir(parents=True, exist_ok=True)
    request_path = REQUESTS_DIR / f"{request_id}.md"
    request_path.write_text(_request_markdown(request), encoding="utf-8")
    request["handoff_path"] = str(request_path)
    _append_jsonl(REQUEST_INDEX_PATH, request)
    _write_initial_report(request)
    open_incidents = state.get("open_incidents") if isinstance(state.get("open_incidents"), dict) else {}
    open_incidents[fingerprint] = {
        "request_id": request_id,
        "last_requested_at": request["requested_at"],
        "last_notification_at": request["requested_at"],
        "status": request["status"],
    }
    _write_json_atomic(STATE_PATH, {"schema_version": SCHEMA_VERSION, "open_incidents": open_incidents})
    queue_administrator_notification(request, report_path=REPORTS_DIR / f"{request_id}.md")
    return request


def _write_initial_report(request: Mapping[str, object]) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"{request['request_id']}.md"
    report_path.write_text(
        "\n".join(
            [
                f"# Improvement report: {request['request_id']}",
                "",
                f"- Status: `{request['status']}`",
                f"- Severity: `{request['severity']}`",
                f"- Started at (UTC): {request['requested_at']}",
                "",
                "## Alert evidence",
                "",
                *[f"- {_safe_text(item)}" for item in request.get("evidence", []) if _safe_text(item)],
                "",
                "## Investigation result",
                "",
                "Pending Codex or operator investigation.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    _append_jsonl(
        REPORT_INDEX_PATH,
        {
            "schema_version": SCHEMA_VERSION,
            "request_id": request["request_id"],
            "status": request["status"],
            "severity": request["severity"],
            "reported_at": request["requested_at"],
            "report_path": str(report_path),
        },
    )
    return report_path


def record_improvement_report(
    *,
    request_id: str,
    status: str,
    summary: str,
    verification: str,
    now: datetime | None = None,
    notification_kind: str = "report",
) -> Path:
    """Append a bounded Codex/operator outcome to the durable incident report."""

    normalized_id = _safe_request_id(request_id)
    normalized_status = _safe_text(status, limit=40) or "investigated"
    report_path = REPORTS_DIR / f"{normalized_id}.md"
    if not report_path.exists():
        raise FileNotFoundError(f"unknown incident request: {normalized_id}")
    reported_at = _timestamp(now)
    section = "\n".join(
        [
            "",
            f"## Outcome ({reported_at})",
            "",
            f"- Status: `{normalized_status}`",
            f"- Summary: {_safe_text(summary, limit=1200)}",
            f"- Verification: {_safe_text(verification, limit=1200)}",
        ]
    )
    with report_path.open("a", encoding="utf-8") as stream:
        stream.write(section + "\n")
    entry = {
        "schema_version": SCHEMA_VERSION,
        "request_id": normalized_id,
        "status": normalized_status,
        "reported_at": reported_at,
        "report_path": str(report_path),
        "summary": _safe_text(summary, limit=240),
    }
    _append_jsonl(REPORT_INDEX_PATH, entry)
    queue_administrator_notification(entry, report_path=report_path, kind=notification_kind)
    return report_path


def queue_administrator_notification(
    record: Mapping[str, object], *, report_path: Path, kind: str = "incident"
) -> dict[str, object]:
    """Queue a bounded report notification without persisting recipient or credential data."""

    normalized_kind = _safe_text(kind, limit=30) or "incident"
    preference_enabled = admin_settings.notification_allowed(normalized_kind)
    delivery_status = (
        "suppressed_by_administrator"
        if not preference_enabled
        else "queued"
        if _delivery_configuration()
        else "pending_configuration"
    )
    notification = {
        "schema_version": SCHEMA_VERSION,
        "notification_id": f"mail-{_safe_text(record.get('request_id'), limit=120)}-{_safe_text(kind, limit=30)}-{utc_now().strftime('%Y%m%dT%H%M%S%fZ')}",
        "request_id": _safe_text(record.get("request_id"), limit=120),
        "severity": _safe_text(record.get("severity") or "critical", limit=20),
        "kind": normalized_kind,
        "status": delivery_status,
        "recipient_configured": delivery_status == "queued",
        "attachment_path": str(report_path),
        "created_at": _timestamp(),
        "attempt_count": 0,
    }
    OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
    _write_json_atomic(OUTBOX_DIR / f"{notification['notification_id']}.json", notification)
    _append_jsonl(OUTBOX_INDEX_PATH, notification)
    return notification


def _notification_due(payload: Mapping[str, object], *, now: datetime) -> bool:
    retry_after = _parse_timestamp(payload.get("retry_not_before"))
    return retry_after is None or retry_after <= now


def _notification_presentation(kind: str, severity: str) -> tuple[str, str, str, str]:
    """Return a bounded Japanese email presentation for a notification kind."""

    presentations = {
        "incident": ("重大アラート", "#DC2626", "SMAIの監視で重大な異常を検知しました。", "添付レポートとSMAIの稼働状態を直ちに確認してください。"),
        "repeat": ("未解決アラート", "#D97706", "重大な異常が継続しています。", "未解決の原因と直近の対応状況を確認してください。"),
        "recovery": ("復旧を確認", "#059669", "SMAI Analyticsは正常状態への復帰を観測しました。", "添付レポートで復旧時刻と対応結果を確認してください。"),
        "approval": ("調査を承認", "#2563EB", "管理者がCodex調査依頼を承認しました。", "これは調査承認です。自動修復や再起動の承認ではありません。"),
        "report": ("改善レポート", "#2563EB", "調査または運用対応の結果が記録されました。", "添付レポートで検証結果を確認してください。"),
        "autofix_approval": ("自動修復を承認", "#D97706", "隔離環境での修復案作成が承認されました。", "この承認だけでは、マージ・再起動・pushは行われません。"),
        "autofix_ready": ("修復案を確認", "#D97706", "隔離環境の修復commitが決定的検証を通過しました。", "添付レポートとローカルcommitを確認してから、マージを明示承認してください。"),
        "autofix_merge_approval": ("マージを承認", "#D97706", "指定された修復commitのマージが承認されました。", "対象checkoutまたはcommitが変化した場合、マージは停止します。"),
        "autofix_merged": ("ローカルマージ完了", "#2563EB", "承認済みの修復commitをローカルへfast-forwardしました。", "Analyticsの再起動には、別途配備承認が必要です。"),
        "autofix_deploy_approval": ("配備を承認", "#D97706", "指定された修復commitのAnalytics配備が承認されました。", "事前検査、backup、再起動、health確認はすべてfail-closedで実行されます。"),
        "autofix_applied": ("配備と確認が完了", "#059669", "Analyticsを再起動し、health確認に成功しました。", "添付レポートを確認し、画面確認とGitHubへのpushは手動で判断してください。"),
        "autofix_rolled_back": ("自動ロールバック完了", "#2563EB", "配備確認に失敗したため、修復commitをrevertして復旧を確認しました。", "添付レポートで失敗理由とrollback commitを確認してください。"),
        "autofix_rollback_failed": ("緊急: ロールバック失敗", "#B91C1C", "配備確認と自動ロールバックの両方に失敗しました。", "自動処理を継続せず、直ちに管理者による手動復旧を開始してください。"),
        "autofix_failed": ("自動修復を停止", "#B91C1C", "自動修復は配備を報告せずに停止しました。", "添付レポートの失敗分類を確認し、必要なら新しい承認からやり直してください。"),
        "autofix_cancelled": ("自動修復を取消", "#64748B", "管理者または安全制約により自動修復を取り消しました。", "添付レポートで取消理由と現在の状態を確認してください。"),
    }
    return presentations.get(
        kind,
        (f"{severity} アラート", "#D97706", "SMAI Analyticsから運用通知があります。", "添付レポートで詳細を確認してください。"),
    )


def _attach_inline_image(part: EmailMessage, path: Path, *, cid: str) -> bool:
    """Attach one local PNG to the HTML alternative without making delivery depend on artwork."""

    try:
        data = path.read_bytes()
    except OSError:
        return False
    part.add_related(data, maintype="image", subtype="png", cid=f"<{cid}>", disposition="inline", filename=path.name)
    return True


def _notification_html(
    *,
    request_id: str,
    label: str,
    color: str,
    headline: str,
    action: str,
    issued_at: str,
    brand_cid: str | None,
    repair_cid: str | None,
) -> str:
    """Build the SMAI operations email with an Outlook-friendly table layout."""

    escaped_id = html.escape(request_id)
    brand = (
        f'<img src="cid:{brand_cid}" width="252" alt="SMAI Analytics" style="border:0; display:block; height:auto; max-width:252px;">'
        if brand_cid
        else '<strong style="color:#F8FBFF; font-size:24px; letter-spacing:0.02em;">SMAI Analytics</strong>'
    )
    repair = (
        f'<img src="cid:{repair_cid}" width="148" alt="SMAI operations mascot" style="border:0; display:block; height:auto; margin:0 auto; max-width:148px;">'
        if repair_cid
        else ""
    )
    return (
        '<!doctype html><html lang="ja"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0"></head>'
        '<body style="background:#050B16; margin:0; padding:0;">'
        '<div style="display:none; font-size:1px; color:#050B16; line-height:1px; max-height:0; opacity:0; overflow:hidden;">'
        f'{html.escape(label)} — {html.escape(headline)}</div>'
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#050B16;"><tr><td align="center" style="padding:28px 12px 36px;">'
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="max-width:640px;">'
        f'<tr><td style="background:{color}; font-size:0; height:4px; line-height:4px;">&nbsp;</td></tr>'
        '<tr><td style="background:#091426; border:1px solid #203B5D; border-top:0; border-radius:0 0 18px 18px; overflow:hidden;">'
        f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"><tr><td style="background:#07111F; padding:24px 28px 20px;">{brand}</td></tr>'
        '<tr><td style="padding:26px 28px 8px;">'
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"><tr>'
        f'<td valign="top"><span style="background:{color}; border-radius:999px; color:#FFFFFF; display:inline-block; font-family:Arial, sans-serif; font-size:11px; font-weight:700; letter-spacing:0.1em; padding:8px 12px;">{html.escape(label)}</span></td>'
        '<td align="right" valign="top" style="color:#7F9BB9; font-family:Arial, sans-serif; font-size:10px; line-height:1.5; padding-left:12px;">SMAI 運用通知 / OPERATIONS<br>ローカル運用 / LOCAL-FIRST</td>'
        '</tr></table>'
        f'<h1 style="color:#F8FBFF; font-family:Arial, &quot;Hiragino Kaku Gothic ProN&quot;, Meiryo, sans-serif; font-size:25px; line-height:1.42; margin:20px 0 10px;">{html.escape(headline)}</h1>'
        f'<p style="color:#BED0E6; font-family:Arial, &quot;Hiragino Kaku Gothic ProN&quot;, Meiryo, sans-serif; font-size:15px; line-height:1.8; margin:0;">{html.escape(action)}</p>'
        '</td></tr>'
        f'<tr><td align="center" style="padding:8px 28px 6px;">{repair}</td></tr>'
        '<tr><td style="padding:14px 28px 6px;">'
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#0E213A; border:1px solid #254C73; border-radius:12px;"><tr><td style="padding:16px 17px;">'
        '<p style="color:#52D7EE; font-family:Arial, sans-serif; font-size:10px; font-weight:700; letter-spacing:0.08em; margin:0 0 6px;">障害・ワークフロー ID / INCIDENT ID</p>'
        f'<p style="color:#F8FBFF; font-family:Consolas, &quot;Courier New&quot;, monospace; font-size:13px; line-height:1.55; margin:0; overflow-wrap:anywhere;">{escaped_id}</p>'
        '</td></tr></table></td></tr>'
        '<tr><td style="padding:10px 28px 26px;"><table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"><tr><td style="border-top:1px solid #203B5D; padding-top:16px;">'
        f'<p style="color:#8FA5BE; font-family:Arial, &quot;Hiragino Kaku Gothic ProN&quot;, Meiryo, sans-serif; font-size:12px; line-height:1.65; margin:0 0 8px;">通知時刻: {html.escape(issued_at)}</p>'
        '<p style="color:#8FA5BE; font-family:Arial, &quot;Hiragino Kaku Gothic ProN&quot;, Meiryo, sans-serif; font-size:12px; line-height:1.65; margin:0;">詳細は添付のローカル運用レポートで確認してください。SMAI Analyticsは閲覧専用であり、このメールへの返信は承認操作として扱われません。</p>'
        '</td></tr></table></td></tr></table></td></tr>'
        '<tr><td align="center" style="color:#607A99; font-family:Arial, sans-serif; font-size:11px; line-height:1.5; padding:16px 12px 0;">SMAI Analytics · ローカル運用通知 / LOCAL OPERATIONS</td></tr>'
        '</table></td></tr></table></body></html>'
    )


def _add_branded_html_alternative(
    message: EmailMessage,
    *,
    request_id: str,
    label: str,
    color: str,
    headline: str,
    action: str,
    issued_at: str,
) -> None:
    """Attach the same visual hierarchy and local artwork to every mail type."""

    brand_cid = "smai-analytics-brand"
    repair_cid = "smai-analytics-repair"
    message.add_alternative(
        _notification_html(
            request_id=request_id,
            label=label,
            color=color,
            headline=headline,
            action=action,
            issued_at=issued_at,
            brand_cid=brand_cid if EMAIL_BRAND_IMAGE.is_file() else None,
            repair_cid=repair_cid if EMAIL_REPAIR_IMAGE.is_file() else None,
        ),
        subtype="html",
    )
    html_part = message.get_payload()[-1]
    if isinstance(html_part, EmailMessage):
        _attach_inline_image(html_part, EMAIL_BRAND_IMAGE, cid=brand_cid)
        _attach_inline_image(html_part, EMAIL_REPAIR_IMAGE, cid=repair_cid)


def _build_notification_message(payload: Mapping[str, object], *, sender: str, recipient: str, attachment: Path) -> EmailMessage:
    kind = _safe_text(payload.get("kind") or "incident", limit=30).lower()
    severity = _safe_text(payload.get("severity") or "critical", limit=20).upper()
    request_id = _safe_text(payload.get("request_id"), limit=120)
    subject_prefix = {
        "incident": severity,
        "repeat": "REMINDER",
        "approval": "CODEX APPROVED",
        "report": "REPORT",
        "recovery": "RECOVERED",
        "autofix_approval": "AUTOFIX APPROVED",
        "autofix_ready": "AUTOFIX READY",
        "autofix_merge_approval": "AUTOFIX MERGE APPROVED",
        "autofix_merged": "AUTOFIX MERGED",
        "autofix_deploy_approval": "AUTOFIX DEPLOY APPROVED",
        "autofix_applied": "AUTOFIX APPLIED",
        "autofix_rolled_back": "AUTOFIX ROLLED BACK",
        "autofix_rollback_failed": "AUTOFIX ROLLBACK FAILED",
        "autofix_failed": "AUTOFIX STOPPED",
        "autofix_cancelled": "AUTOFIX CANCELLED",
    }.get(kind, severity)
    label, color, headline, action = _notification_presentation(kind, severity)
    plain_text = "\n\n".join(
        (
            f"SMAI Analytics | {label}",
            headline,
            action,
            f"Incident / Workflow ID: {request_id}",
            "詳細は添付のローカル運用レポートで確認してください。メール返信は承認操作として扱われません。",
        )
    )
    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = f"[SMAI {subject_prefix}] {request_id}"
    message.set_content(plain_text)
    _add_branded_html_alternative(
        message,
        request_id=request_id,
        label=label,
        color=color,
        headline=headline,
        action=action,
        issued_at=_safe_text(payload.get("created_at") or utc_now().isoformat(), limit=80),
    )
    message.add_attachment(
        attachment.read_bytes(),
        maintype="text",
        subtype="markdown",
        filename=attachment.name,
    )
    return message


def _send_message(configuration: Mapping[str, object], message: EmailMessage) -> None:
    """Send a prepared message without exposing account details to callers or logs."""

    with smtplib.SMTP(str(configuration["host"]), int(configuration["port"]), timeout=15) as client:
        client.starttls(context=ssl.create_default_context())
        username = str(configuration.get("username") or "")
        password = str(configuration.get("password") or "")
        if username:
            client.login(username, password)
        client.send_message(message)


def _delivery_failure_category(error: BaseException) -> str:
    """Classify delivery failures without storing provider responses or secrets."""

    if isinstance(error, smtplib.SMTPAuthenticationError):
        return "smtp_authentication"
    if isinstance(error, (smtplib.SMTPConnectError, TimeoutError, ConnectionError, OSError)):
        return "smtp_connection"
    if isinstance(error, smtplib.SMTPException):
        return "smtp_protocol"
    return "unknown"


def _mark_delivery_failure(payload: dict[str, object], *, now: datetime) -> None:
    attempts = int(payload.get("attempt_count") or 0) + 1
    payload["attempt_count"] = attempts
    if attempts >= DELIVERY_RETRY_LIMIT:
        payload["status"] = "delivery_failed"
        payload.pop("retry_not_before", None)
        return
    payload["status"] = "queued"
    payload["retry_not_before"] = _timestamp(now + DELIVERY_RETRY_DELAYS[min(attempts - 1, len(DELIVERY_RETRY_DELAYS) - 1)])


def _request_record(request_id: str) -> dict[str, object]:
    normalized = _safe_text(request_id, limit=120)
    for row in reversed(_load_jsonl(REQUEST_INDEX_PATH)):
        if _safe_text(row.get("request_id"), limit=120) == normalized:
            return row
    return {}


def _queue_repeat_notification(incident: Mapping[str, object], *, now: datetime) -> bool:
    """Queue a reminder for an unresolved critical incident without creating a second Codex draft."""

    fingerprint = _safe_text(incident.get("fingerprint"), limit=100)
    state = _load_json(STATE_PATH)
    open_incidents = state.get("open_incidents") if isinstance(state.get("open_incidents"), dict) else {}
    current = open_incidents.get(fingerprint)
    if not isinstance(current, dict) or current.get("resolved_at"):
        return False
    last_notification = _parse_timestamp(current.get("last_notification_at"))
    if last_notification is not None and now - last_notification < RENOTIFICATION_WINDOW:
        return False
    request_id = _safe_text(current.get("request_id"), limit=120)
    report_path = REPORTS_DIR / f"{request_id}.md"
    if not request_id or not report_path.is_file():
        return False
    request = _request_record(request_id)
    queue_administrator_notification(
        {
            "request_id": request_id,
            "severity": _safe_text(request.get("severity") or incident.get("severity") or "critical", limit=20),
        },
        report_path=report_path,
        kind="repeat",
    )
    current["last_notification_at"] = _timestamp(now)
    open_incidents[fingerprint] = current
    _write_json_atomic(STATE_PATH, {"schema_version": SCHEMA_VERSION, "open_incidents": open_incidents})
    return True


def _queue_recovery_notifications(*, now: datetime) -> int:
    """Record healthy recovery and notify once for each unresolved critical incident."""

    state = _load_json(STATE_PATH)
    open_incidents = state.get("open_incidents") if isinstance(state.get("open_incidents"), dict) else {}
    recovered = 0
    for fingerprint, current in open_incidents.items():
        if not isinstance(current, dict) or current.get("resolved_at"):
            continue
        request_id = _safe_text(current.get("request_id"), limit=120)
        report_path = REPORTS_DIR / f"{request_id}.md"
        if not request_id or not report_path.is_file():
            continue
        with report_path.open("a", encoding="utf-8") as stream:
            stream.write(f"\n## Monitor recovery ({_timestamp(now)})\n\n- Status: `healthy_observed`\n")
        request = _request_record(request_id)
        queue_administrator_notification(
            {"request_id": request_id, "severity": _safe_text(request.get("severity") or "critical", limit=20)},
            report_path=report_path,
            kind="recovery",
        )
        current["resolved_at"] = _timestamp(now)
        current["status"] = "healthy_observed"
        open_incidents[fingerprint] = current
        recovered += 1
    if recovered:
        _write_json_atomic(STATE_PATH, {"schema_version": SCHEMA_VERSION, "open_incidents": open_incidents})
    return recovered


def _record_codex_approval(*, request_id: str, report_path: Path, approved_at: str) -> None:
    """Expose an administrator approval as a separate read-only report timeline event."""

    existing = _load_jsonl(REPORT_INDEX_PATH)
    if any(
        _safe_text(row.get("request_id"), limit=120) == request_id and _safe_text(row.get("status"), limit=40) == "codex_approved"
        for row in existing
    ):
        return
    _append_jsonl(
        REPORT_INDEX_PATH,
        {
            "schema_version": SCHEMA_VERSION,
            "request_id": request_id,
            "status": "codex_approved",
            "reported_at": approved_at,
            "report_path": str(report_path),
            "summary": "Administrator approved the Codex repair request.",
        },
    )


def approve_codex_request(*, request_id: str, now: datetime | None = None) -> Path:
    """Create the only Codex-ready work order, after local administrator approval."""

    normalized_id = _safe_request_id(request_id)
    draft_path = REQUESTS_DIR / f"{normalized_id}.md"
    report_path = REPORTS_DIR / f"{normalized_id}.md"
    if not draft_path.is_file() or not report_path.is_file():
        raise FileNotFoundError(f"unknown incident request: {normalized_id}")
    approved_at = _timestamp(now)
    APPROVALS_DIR.mkdir(parents=True, exist_ok=True)
    approval_path = APPROVALS_DIR / f"{normalized_id}.md"
    if approval_path.is_file():
        _record_codex_approval(request_id=normalized_id, report_path=report_path, approved_at=approved_at)
        return approval_path
    approval_path.write_text(
        "\n".join(
            [
                f"# Approved Codex repair request: {normalized_id}",
                "",
                f"- Approved at (UTC): {approved_at}",
                "- Approval source: local administrator CLI",
                "",
                "## Required boundaries",
                "",
                "1. Read the linked local draft and confirm the incident before changing code.",
                "2. Do not change SMAI calculations, rankings, Forecast semantics, or user experience without separate approval.",
                "3. Assess effects on all affected Analytics features and run deterministic tests.",
                "4. Restart only Analytics when needed and verify http://localhost:8502 in a real browser.",
                "5. Record the result through incident_automation.py report and notify the administrator.",
                "",
                "## Draft",
                "",
                draft_path.read_text(encoding="utf-8"),
            ]
        ),
        encoding="utf-8",
    )
    with report_path.open("a", encoding="utf-8") as stream:
        stream.write(f"\n## Administrator approval ({approved_at})\n\n- Status: `codex_approved`\n")
    _record_codex_approval(request_id=normalized_id, report_path=report_path, approved_at=approved_at)
    request = _request_record(normalized_id)
    queue_administrator_notification(
        {"request_id": normalized_id, "severity": _safe_text(request.get("severity") or "critical", limit=20)},
        report_path=report_path,
        kind="approval",
    )
    return approval_path


def send_gmail_test_email(*, now: datetime | None = None) -> bool:
    """Explicitly send one minimal test email; this command never runs from the scheduler."""

    try:
        configuration = _gmail_delivery_configuration()
    except windows_credentials.CredentialManagerError:
        configuration = None
    if configuration is None:
        return False
    current = now or utc_now()
    message = EmailMessage()
    message["From"] = str(configuration["sender"])
    message["To"] = str(configuration["recipient"])
    message["Subject"] = "[SMAI Analytics][TEST] Gmail notification delivery"
    message.set_content(
        "SMAI Analytics | Gmail 配信テスト\n\n"
        "固定通知先へのテストメールを正常に作成しました。障害データや添付レポートは含みません。\n\n"
        "このメールへの返信は承認操作として扱われません。"
    )
    _add_branded_html_alternative(
        message,
        request_id=f"gmail-test-{current.strftime('%Y%m%dT%H%M%SZ')}",
        label="Gmail 配信テスト / DELIVERY TEST",
        color="#2563EB",
        headline="SMAI Gmail 配信テストを送信しました。",
        action="固定の通知先へ安全に送信できることを確認するテストです。障害データや添付レポートは含みません。",
        issued_at=_timestamp(current),
    )
    result = {
        "schema_version": SCHEMA_VERSION,
        "notification_id": f"mail-test-{current.strftime('%Y%m%dT%H%M%S%fZ')}",
        "kind": "test",
        "status": "test_delivery_failed",
        "created_at": _timestamp(current),
    }
    try:
        _send_message(configuration, message)
    except (OSError, smtplib.SMTPException) as error:
        result["failure_category"] = _delivery_failure_category(error)
    else:
        result["status"] = "test_delivered"
        result["delivered_at"] = _timestamp(current)
    _append_jsonl(OUTBOX_INDEX_PATH, result)
    return result["status"] == "test_delivered"


def deliver_queued_notifications(*, now: datetime | None = None) -> int:
    """Deliver due outbox records only when the local Gmail/SMTP configuration is complete."""

    current = now or utc_now()
    configuration = _delivery_configuration()
    if configuration is None:
        return 0
    delivered = 0
    for outbox_path in sorted(OUTBOX_DIR.glob("mail-*.json")):
        payload = _load_json(outbox_path)
        if payload.get("status") not in {"queued", "pending_configuration"}:
            continue
        if not _notification_due(payload, now=current):
            continue
        payload["status"] = "queued"
        payload["recipient_configured"] = True
        attachment = Path(str(payload.get("attachment_path") or ""))
        if not attachment.is_file() or attachment.parent.resolve() != REPORTS_DIR.resolve():
            payload["status"] = "attachment_unavailable"
            _write_json_atomic(outbox_path, payload)
            _append_jsonl(OUTBOX_INDEX_PATH, payload)
            continue
        try:
            message = _build_notification_message(
                payload,
                sender=str(configuration["sender"]),
                recipient=str(configuration["recipient"]),
                attachment=attachment,
            )
            _send_message(configuration, message)
        except (OSError, smtplib.SMTPException) as error:
            payload["failure_category"] = _delivery_failure_category(error)
            _mark_delivery_failure(payload, now=current)
        else:
            payload["status"] = "delivered"
            payload["delivered_at"] = _timestamp(current)
            payload.pop("failure_category", None)
            payload.pop("retry_not_before", None)
            delivered += 1
        _write_json_atomic(outbox_path, payload)
        _append_jsonl(OUTBOX_INDEX_PATH, payload)
    return delivered


def report_rows(limit: int = 100) -> list[dict[str, object]]:
    """Return the latest report index entries for the Analytics dashboard."""

    return list(reversed(_load_jsonl(REPORT_INDEX_PATH)[-max(0, limit) :]))


def run_once(*, now: datetime | None = None) -> dict[str, object]:
    current = now or utc_now()
    snapshot = health.collect()
    incident = critical_health_incident(snapshot)
    request = create_codex_request(incident, now=current) if incident else None
    auto_repair_approved = False
    if request and admin_settings.auto_repair_candidate_requested():
        config = codex_autofix.load_config()
        if config["enabled"] is True and config["mode"] == "active":
            try:
                codex_autofix.approve_autofix(
                    request_id=str(request["request_id"]),
                    now=current,
                    approval_source="administrator_settings",
                )
                auto_repair_approved = True
            except (OSError, ValueError, codex_autofix.AutofixError):
                # The durable incident and report remain the evidence of record.
                # A malformed/changed Autofix environment must not make a health
                # probe fail or be reported as an approved repair.
                auto_repair_approved = False
    reminder_queued = False
    recovery_queued = 0
    if incident and request is None:
        reminder_queued = _queue_repeat_notification(incident, now=current)
    elif str(snapshot.get("overall") or "").casefold() == "healthy":
        recovery_queued = _queue_recovery_notifications(now=current)
    delivered = deliver_queued_notifications(now=current)
    return {
        "overall": snapshot.get("overall", "unknown"),
        "request_created": bool(request),
        "request_id": request.get("request_id", "") if request else "",
        "auto_repair_approved": auto_repair_approved,
        "reminder_queued": reminder_queued,
        "recovery_queued": recovery_queued,
        "delivered": delivered,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SMAI critical incident automation")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("once", help="Probe health and queue one deduplicated Codex request if critical.")
    report_parser = subparsers.add_parser("report", help="Record a Codex/operator improvement outcome.")
    report_parser.add_argument("--request-id", required=True)
    report_parser.add_argument("--status", required=True)
    report_parser.add_argument("--summary", required=True)
    report_parser.add_argument("--verification", required=True)
    subparsers.add_parser("deliver-email", help="Deliver due local outbox records using protected Gmail/SMTP configuration.")
    subparsers.add_parser("notification-status", help="Show secret-free Gmail/SMTP notification readiness.")
    configure_parser = subparsers.add_parser("configure-gmail", help="Interactively save one fixed Gmail notification account locally.")
    configure_parser.add_argument("--replace", action="store_true", help="Acknowledge replacement of the current fixed Gmail setup.")
    test_parser = subparsers.add_parser("test-gmail", help="Explicitly send one minimal Gmail test message.")
    test_parser.add_argument("--confirm", action="store_true", help="Required because this sends external email.")
    approval_parser = subparsers.add_parser("approve-codex", help="Create an administrator-approved local Codex work order.")
    approval_parser.add_argument("--request-id", required=True)
    autofix_parser = subparsers.add_parser("approve-autofix", help="Approve one isolated Codex Autofix run for 24 hours.")
    autofix_parser.add_argument("--request-id", required=True)
    merge_parser = subparsers.add_parser("approve-autofix-merge", help="Approve one exact verified Autofix commit for merge.")
    merge_parser.add_argument("--request-id", required=True)
    merge_parser.add_argument("--commit", required=True)
    deploy_parser = subparsers.add_parser("approve-autofix-deploy", help="Approve deployment of one exact merged Autofix commit.")
    deploy_parser.add_argument("--request-id", required=True)
    deploy_parser.add_argument("--commit", required=True)
    cancel_parser = subparsers.add_parser("cancel-autofix", help="Cancel an Autofix or merge lease.")
    cancel_parser.add_argument("--request-id", required=True)
    cancel_parser.add_argument("--reason", required=True)
    status_parser = subparsers.add_parser("autofix-status", help="Show one secret-free Autofix state.")
    status_parser.add_argument("--request-id", required=True)
    worker_parser = subparsers.add_parser("autofix-worker", help="Process at most one approved Autofix workflow.")
    worker_parser.add_argument("--dry-run", action="store_true")
    deploy_worker_parser = subparsers.add_parser("autofix-deploy-worker", help="Process at most one approved Analytics deployment.")
    deploy_worker_parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "once":
        print(json.dumps(run_once(), ensure_ascii=False))
        return 0
    if args.command == "report":
        path = record_improvement_report(
            request_id=args.request_id,
            status=args.status,
            summary=args.summary,
            verification=args.verification,
        )
        print(path)
        return 0
    if args.command == "deliver-email":
        print(json.dumps({"delivered": deliver_queued_notifications()}, ensure_ascii=False))
        return 0
    if args.command == "notification-status":
        print(json.dumps(notification_status(), ensure_ascii=False))
        return 0
    if args.command == "configure-gmail":
        if GMAIL_CONFIG_PATH.exists() and not args.replace:
            raise RuntimeError("A fixed Gmail setup already exists. Re-run with --replace to change it.")
        sender = input("Gmail sending address: ").strip()
        recipient = input("Fixed administrator recipient address: ").strip()
        app_password = getpass.getpass("Gmail app password (not stored in this project): ")
        print(json.dumps(configure_fixed_gmail(sender=sender, recipient=recipient, app_password=app_password), ensure_ascii=False))
        return 0
    if args.command == "test-gmail":
        if not args.confirm:
            raise RuntimeError("test-gmail sends external email. Re-run with --confirm after reviewing the recipient.")
        print(json.dumps({"delivered": send_gmail_test_email()}, ensure_ascii=False))
        return 0
    if args.command == "approve-codex":
        approval_path = approve_codex_request(request_id=args.request_id)
        print(approval_path)
        return 0
    if args.command == "approve-autofix":
        print(json.dumps(codex_autofix.approve_autofix(request_id=args.request_id), ensure_ascii=False))
        return 0
    if args.command == "approve-autofix-merge":
        print(
            json.dumps(
                codex_autofix.approve_autofix_merge(request_id=args.request_id, commit=args.commit),
                ensure_ascii=False,
            )
        )
        return 0
    if args.command == "approve-autofix-deploy":
        print(
            json.dumps(
                codex_autofix.approve_autofix_deploy(request_id=args.request_id, commit=args.commit),
                ensure_ascii=False,
            )
        )
        return 0
    if args.command == "cancel-autofix":
        print(
            json.dumps(
                codex_autofix.cancel_autofix(request_id=args.request_id, reason=args.reason),
                ensure_ascii=False,
            )
        )
        return 0
    if args.command == "autofix-status":
        print(json.dumps(codex_autofix.autofix_status(request_id=args.request_id), ensure_ascii=False))
        return 0
    if args.command == "autofix-deploy-worker":
        print(json.dumps(codex_autofix.run_deploy_worker_once(dry_run=args.dry_run), ensure_ascii=False))
        return 0
    print(json.dumps(codex_autofix.run_worker_once(dry_run=args.dry_run), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
