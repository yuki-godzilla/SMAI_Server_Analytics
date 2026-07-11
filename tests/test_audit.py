import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import audit


class AuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="smai-audit-", dir=str(Path.cwd()))
        root = Path(self.temp_dir.name)
        self.original_event_log = audit.EVENT_LOG
        self.original_salt_path = audit.DEVICE_SALT_PATH
        audit.EVENT_LOG = root / "audit" / "events.jsonl"
        audit.DEVICE_SALT_PATH = root / "audit" / "device_salt"

    def tearDown(self) -> None:
        audit.EVENT_LOG = self.original_event_log
        audit.DEVICE_SALT_PATH = self.original_salt_path
        self.temp_dir.cleanup()

    def test_record_event_redacts_sensitive_metadata_keys(self) -> None:
        recorded = audit.record_event(
            user_id="local-user",
            action="research",
            metadata={"safe": "yes", "Api_Token": "do-not-store", "requestBody": "private", "profile": "local"},
        )

        self.assertTrue(recorded)
        event = json.loads(audit.EVENT_LOG.read_text(encoding="utf-8"))
        self.assertEqual(event["metadata"], {"safe": "yes", "profile": "local"})
        self.assertNotIn("do-not-store", audit.EVENT_LOG.read_text(encoding="utf-8"))

    def test_record_event_is_best_effort_when_runtime_write_fails(self) -> None:
        with patch("audit.Path.open", side_effect=PermissionError("locked")):
            self.assertFalse(audit.record_event(user_id="local-user", action="test"))


if __name__ == "__main__":
    unittest.main()
