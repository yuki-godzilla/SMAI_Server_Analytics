import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from smai_analytics.monitoring import task_monitor
from smai_analytics.operations import host_maintenance


class HostMaintenanceTests(unittest.TestCase):
    def test_preflight_allows_quiet_session_state_with_fresh_healthy_snapshot(self) -> None:
        now = datetime(2026, 7, 15, 4, tzinfo=UTC)
        activity = {
            "sessions": {
                "old": {"last_seen_at": (now - timedelta(minutes=16)).isoformat()},
            },
            "operations": {},
        }
        health = {"checked_at": (now - timedelta(minutes=5)).isoformat(), "overall": "healthy"}

        result = host_maintenance.evaluate_preflight(activity, health, now=now)

        self.assertTrue(result.safe_to_restart)
        self.assertEqual("ready", result.status)

    def test_preflight_defers_for_recent_session_or_stale_health(self) -> None:
        now = datetime(2026, 7, 15, 4, tzinfo=UTC)
        activity = {
            "sessions": {"active": {"last_seen_at": (now - timedelta(minutes=2)).isoformat()}},
            "operations": {"op": {"started_at": now.isoformat()}},
        }
        health = {"checked_at": (now - timedelta(minutes=11)).isoformat(), "overall": "healthy"}

        result = host_maintenance.evaluate_preflight(activity, health, now=now)

        self.assertFalse(result.safe_to_restart)
        self.assertIn("active_sessions", result.blockers)
        self.assertIn("busy_operations", result.blockers)
        self.assertIn("health_snapshot_stale", result.blockers)

    def test_write_preflight_uses_atomic_state_file(self) -> None:
        result = host_maintenance.Preflight(
            checked_at="2026-07-15T04:00:00+00:00",
            status="ready",
            safe_to_restart=True,
            blockers=(),
            active_sessions=0,
            busy_operations=0,
        )
        with tempfile.TemporaryDirectory(prefix="smai-host-maintenance-") as directory:
            path = Path(directory) / "state.json"
            self.assertTrue(host_maintenance.write_preflight(result, path))
            self.assertIn('"safe_to_restart": true', path.read_text(encoding="utf-8"))

    def test_host_monitor_uses_recurring_freshness_policy(self) -> None:
        now = datetime(2026, 7, 15, 4, tzinfo=UTC)
        status, _detail = task_monitor.classify_task(
            "SMAI-Host-Monitor",
            {"last_result": "0", "last_run_time": (now - timedelta(minutes=11)).isoformat()},
            path_ok=True,
            now=now,
        )
        self.assertEqual("degraded", status)


if __name__ == "__main__":
    unittest.main()
