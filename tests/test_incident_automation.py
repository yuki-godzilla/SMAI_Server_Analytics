from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import incident_automation


class IncidentAutomationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="smai-incident-", dir=str(Path.cwd()))
        root = Path(self.temp_dir.name)
        self.paths = {
            "INCIDENT_ROOT": incident_automation.INCIDENT_ROOT,
            "REQUESTS_DIR": incident_automation.REQUESTS_DIR,
            "REPORTS_DIR": incident_automation.REPORTS_DIR,
            "OUTBOX_DIR": incident_automation.OUTBOX_DIR,
            "STATE_PATH": incident_automation.STATE_PATH,
            "REQUEST_INDEX_PATH": incident_automation.REQUEST_INDEX_PATH,
            "REPORT_INDEX_PATH": incident_automation.REPORT_INDEX_PATH,
            "OUTBOX_INDEX_PATH": incident_automation.OUTBOX_INDEX_PATH,
            "GMAIL_CONFIG_PATH": incident_automation.GMAIL_CONFIG_PATH,
            "APPROVALS_DIR": incident_automation.APPROVALS_DIR,
        }
        incident_automation.INCIDENT_ROOT = root
        incident_automation.REQUESTS_DIR = root / "codex_requests"
        incident_automation.REPORTS_DIR = root / "reports"
        incident_automation.OUTBOX_DIR = root / "admin_outbox"
        incident_automation.STATE_PATH = root / "state.json"
        incident_automation.REQUEST_INDEX_PATH = root / "codex_requests.jsonl"
        incident_automation.REPORT_INDEX_PATH = root / "improvement_reports.jsonl"
        incident_automation.OUTBOX_INDEX_PATH = root / "admin_notifications.jsonl"
        incident_automation.GMAIL_CONFIG_PATH = root / "gmail_notification.json"
        incident_automation.APPROVALS_DIR = root / "codex_approvals"

    def tearDown(self) -> None:
        for name, value in self.paths.items():
            setattr(incident_automation, name, value)
        self.temp_dir.cleanup()

    def test_critical_health_creates_one_deduplicated_codex_request_and_report(self) -> None:
        incident = incident_automation.critical_health_incident(
            {
                "overall": "critical",
                "checked_at": "2026-07-12T00:00:00+00:00",
                "checks": [{"name": "Streamlit health", "status": "failed"}],
            }
        )
        now = datetime(2026, 7, 12, 0, 1, tzinfo=UTC)

        request = incident_automation.create_codex_request(incident or {}, now=now)
        duplicate = incident_automation.create_codex_request(incident or {}, now=now + timedelta(minutes=5))

        self.assertIsNotNone(request)
        self.assertIsNone(duplicate)
        self.assertTrue(Path(str(request["handoff_path"])).is_file())
        report = incident_automation.REPORTS_DIR / f"{request['request_id']}.md"
        self.assertIn("Pending Codex", report.read_text(encoding="utf-8"))
        outbox = json.loads(next(incident_automation.OUTBOX_DIR.glob("mail-*.json")).read_text(encoding="utf-8"))
        self.assertEqual(outbox["status"], "pending_configuration")
        self.assertFalse(outbox["recipient_configured"])

    def test_healthy_snapshot_does_not_create_incident(self) -> None:
        self.assertIsNone(incident_automation.critical_health_incident({"overall": "healthy", "checks": []}))

    def test_record_report_appends_outcome_and_queues_notification(self) -> None:
        incident = {
            "severity": "critical",
            "source": "health",
            "fingerprint": "critical-health-test",
            "title": "Test",
            "evidence": ["TCP 8501"],
        }
        request = incident_automation.create_codex_request(incident, now=datetime(2026, 7, 12, tzinfo=UTC))

        report_path = incident_automation.record_improvement_report(
            request_id=str(request["request_id"]),
            status="resolved",
            summary="Restarted a safe local service.",
            verification="health.py returned healthy.",
            now=datetime(2026, 7, 12, 0, 10, tzinfo=UTC),
        )

        contents = report_path.read_text(encoding="utf-8")
        self.assertIn("Status: `resolved`", contents)
        self.assertIn("health.py returned healthy.", contents)
        self.assertEqual(len(incident_automation.report_rows()), 2)

    @patch.dict("os.environ", {}, clear=True)
    def test_delivery_is_disabled_without_explicit_smtp_configuration(self) -> None:
        self.assertEqual(incident_automation.deliver_queued_notifications(), 0)

    def test_fixed_gmail_configuration_keeps_the_app_password_out_of_runtime(self) -> None:
        stored: dict[str, str] = {}

        def write_secret(*, target: str, username: str, secret: str) -> None:
            stored.update(target=target, username=username, secret=secret)

        with patch.object(incident_automation.windows_credentials, "write_generic_secret", side_effect=write_secret), patch.object(
            incident_automation, "_read_gmail_secret", return_value=("admin@example.com", "app-password")
        ):
            status = incident_automation.configure_fixed_gmail(
                sender="admin@example.com",
                recipient="notify@example.com",
                app_password="app-password",
            )

        persisted = json.loads(incident_automation.GMAIL_CONFIG_PATH.read_text(encoding="utf-8"))
        self.assertEqual("SMAI-Analytics-Gmail-SMTP", stored["target"])
        self.assertEqual("app-password", stored["secret"])
        self.assertNotIn("app-password", incident_automation.GMAIL_CONFIG_PATH.read_text(encoding="utf-8"))
        self.assertEqual("ready", status["status"])
        self.assertNotIn("notify@example.com", json.dumps(status, ensure_ascii=False))

    def test_gmail_app_password_is_normalized_when_google_displays_it_in_groups(self) -> None:
        incident_automation._write_json_atomic(
            incident_automation.GMAIL_CONFIG_PATH,
            {
                "provider": "gmail_smtp",
                "sender": "admin@example.com",
                "recipient": "notify@example.com",
                "host": "smtp.gmail.com",
                "port": 587,
                "credential_target": "test-target",
            },
        )
        with patch.object(incident_automation, "_read_gmail_secret", return_value=("admin@example.com", "abcd efgh ijkl mnop")):
            configuration = incident_automation._gmail_delivery_configuration()

        self.assertIsNotNone(configuration)
        self.assertEqual("abcdefghijklmnop", configuration["password"])

    def test_gmail_delivery_uses_protected_configuration_and_records_success(self) -> None:
        incident = {
            "severity": "critical",
            "source": "health",
            "fingerprint": "critical-health-mail",
            "title": "Test",
            "evidence": ["TCP 8501"],
        }
        request = incident_automation.create_codex_request(incident, now=datetime(2026, 7, 12, tzinfo=UTC))
        configuration = {
            "provider": "gmail_smtp",
            "recipient": "notify@example.com",
            "sender": "admin@example.com",
            "host": "smtp.gmail.com",
            "port": 587,
            "username": "admin@example.com",
            "password": "app-password",
        }
        with patch.object(incident_automation, "_delivery_configuration", return_value=configuration), patch.object(
            incident_automation, "_send_message"
        ) as send:
            delivered = incident_automation.deliver_queued_notifications(now=datetime(2026, 7, 12, 0, 1, tzinfo=UTC))

        payload = json.loads(next(incident_automation.OUTBOX_DIR.glob("mail-*.json")).read_text(encoding="utf-8"))
        self.assertEqual(1, delivered)
        self.assertEqual("delivered", payload["status"])
        self.assertEqual(str(request["request_id"]), payload["request_id"])
        self.assertNotIn("app-password", json.dumps(payload, ensure_ascii=False))
        send.assert_called_once()

    def test_administrator_approval_creates_a_separate_codex_ready_work_order(self) -> None:
        incident = {
            "severity": "critical",
            "source": "health",
            "fingerprint": "critical-health-approval",
            "title": "Test",
            "evidence": ["TCP 8501"],
        }
        request = incident_automation.create_codex_request(incident, now=datetime(2026, 7, 12, tzinfo=UTC))

        approval = incident_automation.approve_codex_request(
            request_id=str(request["request_id"]), now=datetime(2026, 7, 12, 0, 2, tzinfo=UTC)
        )

        self.assertTrue(approval.is_file())
        self.assertIn("Approved Codex repair request", approval.read_text(encoding="utf-8"))
        self.assertIn("codex_approved", (incident_automation.REPORTS_DIR / f"{request['request_id']}.md").read_text(encoding="utf-8"))

    def test_unresolved_critical_is_reminded_once_and_healthy_recovery_is_recorded_once(self) -> None:
        incident = {
            "severity": "critical",
            "source": "health",
            "fingerprint": "critical-health-reminder",
            "title": "Test",
            "evidence": ["TCP 8501"],
        }
        started = datetime(2026, 7, 12, tzinfo=UTC)
        request = incident_automation.create_codex_request(incident, now=started)

        self.assertTrue(incident_automation._queue_repeat_notification(incident, now=started + timedelta(minutes=15)))
        self.assertFalse(incident_automation._queue_repeat_notification(incident, now=started + timedelta(minutes=16)))
        self.assertEqual(1, incident_automation._queue_recovery_notifications(now=started + timedelta(minutes=20)))
        self.assertEqual(0, incident_automation._queue_recovery_notifications(now=started + timedelta(minutes=21)))

        kinds = [
            json.loads(path.read_text(encoding="utf-8"))["kind"]
            for path in incident_automation.OUTBOX_DIR.glob("mail-*.json")
        ]
        self.assertEqual(1, kinds.count("repeat"))
        self.assertEqual(1, kinds.count("recovery"))
        report = (incident_automation.REPORTS_DIR / f"{request['request_id']}.md").read_text(encoding="utf-8")
        self.assertIn("Monitor recovery", report)

    def test_delivery_failure_is_retried_then_marked_failed(self) -> None:
        incident = {
            "severity": "critical",
            "source": "health",
            "fingerprint": "critical-health-retry",
            "title": "Test",
            "evidence": ["TCP 8501"],
        }
        started = datetime(2026, 7, 12, tzinfo=UTC)
        incident_automation.create_codex_request(incident, now=started)
        configuration = {
            "provider": "gmail_smtp",
            "recipient": "notify@example.com",
            "sender": "admin@example.com",
            "host": "smtp.gmail.com",
            "port": 587,
            "username": "admin@example.com",
            "password": "app-password",
        }
        with patch.object(incident_automation, "_delivery_configuration", return_value=configuration), patch.object(
            incident_automation, "_send_message", side_effect=OSError("network unavailable")
        ) as send:
            for attempt, minute in enumerate((0, 5, 20), start=1):
                self.assertEqual(0, incident_automation.deliver_queued_notifications(now=started + timedelta(minutes=minute)))
                payload = json.loads(next(incident_automation.OUTBOX_DIR.glob("mail-*.json")).read_text(encoding="utf-8"))
                self.assertEqual(attempt, payload["attempt_count"])

        self.assertEqual(3, send.call_count)
        self.assertEqual("delivery_failed", payload["status"])
        self.assertNotIn("retry_not_before", payload)

    def test_gmail_test_delivery_records_a_sanitized_failure_category(self) -> None:
        configuration = {
            "provider": "gmail_smtp",
            "recipient": "notify@example.com",
            "sender": "admin@example.com",
            "host": "smtp.gmail.com",
            "port": 587,
            "username": "admin@example.com",
            "password": "app-password",
        }
        error = __import__("smtplib").SMTPAuthenticationError(535, b"provider message is not retained")
        with patch.object(incident_automation, "_gmail_delivery_configuration", return_value=configuration), patch.object(
            incident_automation, "_send_message", side_effect=error
        ):
            self.assertFalse(incident_automation.send_gmail_test_email(now=datetime(2026, 7, 12, tzinfo=UTC)))

        row = incident_automation._load_jsonl(incident_automation.OUTBOX_INDEX_PATH)[-1]
        self.assertEqual("test_delivery_failed", row["status"])
        self.assertEqual("smtp_authentication", row["failure_category"])
        self.assertNotIn("provider message", json.dumps(row, ensure_ascii=False))

    def test_notification_subjects_distinguish_the_incident_workflow_steps(self) -> None:
        incident_automation.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        attachment = incident_automation.REPORTS_DIR / "workflow-test.md"
        attachment.write_text("TEST ONLY", encoding="utf-8")
        expected_prefixes = {
            "incident": "[SMAI CRITICAL]",
            "repeat": "[SMAI REMINDER]",
            "approval": "[SMAI CODEX APPROVED]",
            "report": "[SMAI REPORT]",
            "recovery": "[SMAI RECOVERED]",
        }
        for kind, prefix in expected_prefixes.items():
            message = incident_automation._build_notification_message(
                {"kind": kind, "severity": "critical", "request_id": "incident-test"},
                sender="admin@example.com",
                recipient="notify@example.com",
                attachment=attachment,
            )
            self.assertTrue(str(message["Subject"]).startswith(prefix))


if __name__ == "__main__":
    unittest.main()
