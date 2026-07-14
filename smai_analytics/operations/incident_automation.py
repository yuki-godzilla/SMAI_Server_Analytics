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
from . import windows_credentials

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


def _read_gmail_secret(target: str) -> tuple[str, str] | None:
    """Read the app password only at delivery time; callers must not log it."""

    return windows_credentials.read_generic_secret(target=target)


def configure_fixed_gmail(*, sender: str, recipient: str, app_password: str) -> dict[str, object]:
    """Persist one local Gmail recipient and protect its app password in Windows."""

    normalized_sender = _valid_email(sender)
    normalized_recipient = _valid_email(recipient)
    if not app_password.strip():
        raise ValueError("A Gmail app password is required.")
    windows_credentials.write_generic_secret(
        target=GMAIL_CREDENTIAL_TARGET,
        username=normalized_sender,
        secret=app_password.strip(),
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
    *, request_id: str, status: str, summary: str, verification: str, now: datetime | None = None
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
    queue_administrator_notification(entry, report_path=report_path, kind="report")
    return report_path


def queue_administrator_notification(
    record: Mapping[str, object], *, report_path: Path, kind: str = "incident"
) -> dict[str, object]:
    """Queue a bounded report notification without persisting recipient or credential data."""

    delivery_status = "queued" if _delivery_configuration() else "pending_configuration"
    notification = {
        "schema_version": SCHEMA_VERSION,
        "notification_id": f"mail-{_safe_text(record.get('request_id'), limit=120)}-{_safe_text(kind, limit=30)}-{utc_now().strftime('%Y%m%dT%H%M%S%fZ')}",
        "request_id": _safe_text(record.get("request_id"), limit=120),
        "severity": _safe_text(record.get("severity") or "critical", limit=20),
        "kind": _safe_text(kind, limit=30) or "incident",
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


def _build_notification_message(payload: Mapping[str, object], *, sender: str, recipient: str, attachment: Path) -> EmailMessage:
    kind = _safe_text(payload.get("kind") or "incident", limit=30).lower()
    severity = _safe_text(payload.get("severity") or "critical", limit=20).upper()
    request_id = _safe_text(payload.get("request_id"), limit=120)
    subject_prefix = "RECOVERED" if kind == "recovery" else severity
    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = f"[SMAI {subject_prefix}] {request_id}"
    if kind == "recovery":
        message.set_content(
            "SMAI Analytics observed a healthy recovery for this incident. "
            "The attached local report remains the audit record."
        )
    elif kind == "report":
        message.set_content(
            "SMAI Analytics recorded a bounded investigation outcome. "
            "The attached local report is available for administrator review."
        )
    else:
        message.set_content(
            "SMAI Analytics detected a critical operational incident. "
            "The attached local report contains only bounded operational evidence."
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
    request = _request_record(normalized_id)
    queue_administrator_notification(
        {"request_id": normalized_id, "severity": _safe_text(request.get("severity") or "critical", limit=20)},
        report_path=report_path,
        kind="report",
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
    message.set_content("This is an explicit Gmail delivery test from SMAI Analytics. No incident data is attached.")
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
    approval_path = approve_codex_request(request_id=args.request_id)
    print(approval_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
