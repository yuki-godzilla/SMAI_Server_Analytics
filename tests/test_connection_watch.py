import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

import connection_watch


class ConnectionWatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="smai-connections-", dir=str(Path.cwd()))
        self.path = Path(self.temp_dir.name) / "connections" / "watch_state.json"
        self.now = datetime(2026, 7, 12, 1, tzinfo=UTC)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_observe_tracks_current_and_cumulative_devices_by_type(self) -> None:
        result = connection_watch.observe(
            (
                {"session_id": "pc-1", "client_type": "desktop", "device_id": "device-pc", "status": "ok"},
                {"session_id": "phone-1", "client_type": "smartphone", "device_id": "device-phone", "status": "ok"},
                {"session_id": "tablet-1", "client_type": "tablet", "device_id": "", "status": "ok"},
            ),
            self.path,
            observed_at=self.now,
        )

        counts = connection_watch.summary(result["state"])
        self.assertTrue(result["ok"])
        self.assertEqual(counts["current"], {"desktop": 1, "smartphone": 1, "tablet": 1})
        self.assertEqual(counts["cumulative"], {"desktop": 1, "smartphone": 1, "tablet": 0})
        self.assertEqual(counts["unlinked_current"], {"desktop": 0, "smartphone": 0, "tablet": 1})
        self.assertEqual(counts["total_cumulative"], 2)

    def test_observe_records_state_changes_and_missing_sessions_without_guessing_disconnect(self) -> None:
        first = connection_watch.observe(
            ({"session_id": "pc-1", "client_type": "desktop", "device_id": "device-pc", "status": "ok"},),
            self.path,
            observed_at=self.now,
        )
        second = connection_watch.observe(
            ({"session_id": "pc-1", "client_type": "desktop", "device_id": "device-pc", "status": "degraded"},),
            self.path,
            observed_at=self.now + timedelta(seconds=5),
        )
        third = connection_watch.observe((), self.path, observed_at=self.now + timedelta(seconds=10))

        events = third["state"]["events"]
        self.assertEqual([event["event"] for event in events], ["observed", "state_changed", "observation_lost"])
        self.assertEqual(events[-1]["status"], "unknown")
        self.assertEqual(connection_watch.summary(second["state"])["current"]["desktop"], 0)
        self.assertEqual(connection_watch.summary(third["state"])["cumulative"]["desktop"], 1)
        self.assertTrue(first["ok"])

    def test_corrupt_existing_state_is_not_overwritten_or_treated_as_empty(self) -> None:
        self.path.parent.mkdir(parents=True)
        self.path.write_text("not json", encoding="utf-8")

        result = connection_watch.observe(
            ({"session_id": "pc-1", "client_type": "desktop", "device_id": "device-pc", "status": "ok"},),
            self.path,
            observed_at=self.now,
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "state unreadable")
        self.assertEqual(self.path.read_text(encoding="utf-8"), "not json")

    def test_read_distinguishes_missing_history_from_invalid_history(self) -> None:
        missing = connection_watch.read(self.path)
        self.assertTrue(missing["ok"])
        self.assertFalse(missing["available"])

        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({"version": 0}), encoding="utf-8")
        invalid = connection_watch.read(self.path)
        self.assertFalse(invalid["ok"])
        self.assertEqual(invalid["reason"], "state invalid")

        self.path.write_text(
            json.dumps({"version": 1, "sessions": {}, "devices": {}, "events": ["corrupt"]}),
            encoding="utf-8",
        )
        malformed = connection_watch.read(self.path)
        self.assertFalse(malformed["ok"])
        self.assertEqual(malformed["reason"], "state invalid")


if __name__ == "__main__":
    unittest.main()
