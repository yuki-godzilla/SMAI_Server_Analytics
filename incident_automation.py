"""Fail-closed incident handoff, report retention, and administrator mail outbox.

Analytics never imports SMAI private modules or changes SMAI source code.  A
critical health condition becomes a durable, deduplicated Codex investigation
request in the local Runtime directory.  A separate Codex or operator process
can then investigate and register its outcome with the ``report`` command.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import smtplib
import ssl
import sys
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from pathlib import Path
from typing import Iterable, Mapping

import health

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
DEDUPLICATION_WINDOW = timedelta(minutes=30)
SCHEMA_VERSION = 1


def utc_now() -> datetime:
    return datetime.now(UTC)


def _timestamp(value: datetime | None = None) -> str:
    return (value or utc_now()).isoformat()


def _safe_text(value: object, *, limit: int = 240) -> str:
    return str(value).replace("\r", " ").replace("\n", " ").strip()[:limit]


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
            "1. Confirm the alert with SMAI health, audit, and relevant runtime logs.",
            "2. Identify the root cause without changing investment calculations automatically.",
            "3. Apply the smallest safe fix only when the failure is reproducible and in scope.",
            "4. Run targeted deterministic checks and record results in an improvement report.",
            "5. Do not expose credentials, user content, prompt text, or raw provider responses.",
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

    normalized_id = _safe_text(request_id, limit=120)
    if not normalized_id:
        raise ValueError("request_id is required")
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
    queue_administrator_notification(entry, report_path=report_path)
    return report_path


def queue_administrator_notification(record: Mapping[str, object], *, report_path: Path) -> dict[str, object]:
    """Queue a report attachment; delivery is opt-in and never logs SMTP secrets."""

    recipient = os.environ.get("SMAI_ADMIN_EMAIL_TO", "").strip()
    delivery_status = "pending_configuration" if not recipient else "queued"
    notification = {
        "schema_version": SCHEMA_VERSION,
        "notification_id": f"mail-{_safe_text(record.get('request_id'), limit=120)}-{utc_now().strftime('%Y%m%dT%H%M%SZ')}",
        "request_id": _safe_text(record.get("request_id"), limit=120),
        "severity": _safe_text(record.get("severity") or "critical", limit=20),
        "status": delivery_status,
        "recipient_configured": bool(recipient),
        "attachment_path": str(report_path),
        "created_at": _timestamp(),
    }
    OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
    _write_json_atomic(OUTBOX_DIR / f"{notification['notification_id']}.json", notification)
    _append_jsonl(OUTBOX_INDEX_PATH, notification)
    return notification


def deliver_queued_notifications() -> int:
    """Send queued reports only when explicit SMTP configuration is complete."""

    recipient = os.environ.get("SMAI_ADMIN_EMAIL_TO", "").strip()
    sender = os.environ.get("SMAI_ADMIN_EMAIL_FROM", "").strip()
    host = os.environ.get("SMAI_ADMIN_SMTP_HOST", "").strip()
    if not recipient or not sender or not host:
        return 0
    port = int(os.environ.get("SMAI_ADMIN_SMTP_PORT", "587"))
    username = os.environ.get("SMAI_ADMIN_SMTP_USERNAME", "").strip()
    password = os.environ.get("SMAI_ADMIN_SMTP_PASSWORD", "")
    delivered = 0
    for outbox_path in sorted(OUTBOX_DIR.glob("mail-*.json")):
        payload = _load_json(outbox_path)
        if payload.get("status") != "queued":
            continue
        attachment = Path(str(payload.get("attachment_path") or ""))
        if not attachment.is_file() or attachment.parent != REPORTS_DIR:
            payload["status"] = "attachment_unavailable"
            _write_json_atomic(outbox_path, payload)
            continue
        message = EmailMessage()
        message["From"] = sender
        message["To"] = recipient
        message["Subject"] = f"[SMAI {payload.get('severity', 'critical').upper()}] {payload.get('request_id', '')}"
        message.set_content("SMAI Analytics generated an incident report. The local report is attached.")
        message.add_attachment(
            attachment.read_bytes(),
            maintype="text",
            subtype="markdown",
            filename=attachment.name,
        )
        try:
            with smtplib.SMTP(host, port, timeout=15) as client:
                client.starttls(context=ssl.create_default_context())
                if username:
                    client.login(username, password)
                client.send_message(message)
        except (OSError, smtplib.SMTPException):
            payload["status"] = "delivery_failed"
        else:
            payload["status"] = "delivered"
            payload["delivered_at"] = _timestamp()
            delivered += 1
        _write_json_atomic(outbox_path, payload)
        _append_jsonl(OUTBOX_INDEX_PATH, payload)
    return delivered


def report_rows(limit: int = 100) -> list[dict[str, object]]:
    """Return the latest report index entries for the Analytics dashboard."""

    return list(reversed(_load_jsonl(REPORT_INDEX_PATH)[-max(0, limit) :]))


def run_once(*, now: datetime | None = None) -> dict[str, object]:
    snapshot = health.collect()
    incident = critical_health_incident(snapshot)
    request = create_codex_request(incident, now=now) if incident else None
    return {
        "overall": snapshot.get("overall", "unknown"),
        "request_created": bool(request),
        "request_id": request.get("request_id", "") if request else "",
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
    subparsers.add_parser("deliver-email", help="Deliver queued reports when SMTP environment variables are configured.")
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
    print(json.dumps({"delivered": deliver_queued_notifications()}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
