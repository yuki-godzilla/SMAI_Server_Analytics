import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

import telemetry


def snapshot(at: datetime, *, overall: str = "healthy", l1: str = "ok", latency: int = 40) -> dict[str, object]:
    return {
        "checked_at": at.isoformat(),
        "overall": overall,
        "checks": [
            {"name": "Streamlit health", "level": "L1", "status": l1, "latency_ms": latency},
            {"name": "Streamlit page", "level": "L2", "status": "ok", "latency_ms": latency + 10},
            {"name": "user data", "level": "L3", "status": "ok", "latency_ms": 3},
        ],
        "storage": [{"name": "Runtime", "status": "ok", "free_percent": 61.5, "free_bytes": 1000}],
    }


class TelemetryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="smai-telemetry-", dir=str(Path.cwd()))
        self.runtime = Path(self.temp_dir.name) / "runtime"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_rollup_preserves_worst_check_state_and_latency_percentile(self) -> None:
        first = datetime(2026, 7, 12, 9, 0, tzinfo=UTC)
        self.assertEqual(telemetry.record_health_snapshot(snapshot(first), self.runtime)["status"], "healthy")
        self.assertEqual(
            telemetry.record_health_snapshot(snapshot(first + timedelta(minutes=1), overall="critical", l1="failed", latency=180), self.runtime)["status"],
            "healthy",
        )
        self.assertEqual(telemetry.record_health_snapshot(snapshot(first + timedelta(minutes=5), latency=55), self.runtime)["status"], "healthy")

        rows = telemetry.read_health_rollups(self.runtime, now=first + timedelta(minutes=6), window=timedelta(minutes=10))
        self.assertEqual(len(rows), 2)
        self.assertEqual(telemetry.level_status(rows[0], "L1"), "critical")
        self.assertEqual(rows[0]["latency_ms"]["Streamlit health"]["p95_ms"], 180)
        self.assertEqual(rows[0]["storage"][0]["free_percent"], 61.5)

    def test_missing_rollups_are_not_counted_as_healthy(self) -> None:
        start = datetime(2026, 7, 12, 9, 0, tzinfo=UTC)
        rows = telemetry.read_health_rollups(self.runtime, now=start, window=timedelta(hours=1))
        summary = telemetry.window_summary(rows, window=timedelta(hours=1))
        self.assertEqual(rows, [])
        self.assertEqual(summary["coverage_percent"], 0.0)
        self.assertEqual(summary["overall"]["healthy"], 0)

    def test_invalid_timestamp_fails_closed(self) -> None:
        self.assertEqual(
            telemetry.record_health_snapshot({"checked_at": "not-a-time"}, self.runtime)["status"],
            "unknown",
        )


if __name__ == "__main__":
    unittest.main()
