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
        }
        incident_automation.INCIDENT_ROOT = root
        incident_automation.REQUESTS_DIR = root / "codex_requests"
        incident_automation.REPORTS_DIR = root / "reports"
        incident_automation.OUTBOX_DIR = root / "admin_outbox"
        incident_automation.STATE_PATH = root / "state.json"
        incident_automation.REQUEST_INDEX_PATH = root / "codex_requests.jsonl"
        incident_automation.REPORT_INDEX_PATH = root / "improvement_reports.jsonl"
        incident_automation.OUTBOX_INDEX_PATH = root / "admin_notifications.jsonl"

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


if __name__ == "__main__":
    unittest.main()
