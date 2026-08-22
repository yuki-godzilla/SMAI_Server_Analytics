"""Regression tests for the detailed Operations dashboard snapshot."""

import unittest
from unittest import mock

from smai_analytics.ui import web_dashboard


class WebDashboardSnapshotTests(unittest.TestCase):
    def test_operations_snapshot_includes_task_observation_history(self) -> None:
        """Task history must be readable when the detailed dashboard is rendered."""

        history = [{"observed_at": "2026-07-17T00:00:00+00:00", "tasks": []}]
        with (
            mock.patch.object(web_dashboard, "collect_summary_snapshot", return_value={}),
            mock.patch.object(web_dashboard, "read_events", return_value=[]),
            mock.patch.object(web_dashboard.incident_automation, "report_rows", return_value=[]),
            mock.patch.object(
                web_dashboard.incident_automation,
                "notification_status",
                return_value={"status": "healthy", "detail": ""},
            ),
            mock.patch.object(web_dashboard.telemetry, "read_health_rollups", return_value=[]),
            mock.patch.object(web_dashboard.connection_watch, "read", return_value=[]),
            mock.patch.object(web_dashboard.task_monitor, "read_observations", return_value=history) as read_observations,
            mock.patch.object(web_dashboard, "task_rows", return_value=[]),
            mock.patch.object(web_dashboard, "recent_logs", return_value=[]),
        ):
            snapshot = web_dashboard.collect_operations_snapshot()

        self.assertEqual(snapshot["task_history"], history)
        read_observations.assert_called_once_with(web_dashboard.RUNTIME_ROOT, window=web_dashboard.timedelta(days=30))
