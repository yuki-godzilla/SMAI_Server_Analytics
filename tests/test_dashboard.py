import unittest
from datetime import UTC, datetime
from types import SimpleNamespace

import dashboard


class DashboardFormattingTests(unittest.TestCase):
    def test_compact_id_keeps_short_value(self) -> None:
        self.assertEqual(dashboard.compact_id("session-1"), "session-1")

    def test_compact_id_shortens_long_value(self) -> None:
        self.assertEqual(dashboard.compact_id("1234567890abcdefghijklmnop"), "12345678…klmnop")

    def test_ui_scale_expands_4k_content_but_has_a_safe_cap(self) -> None:
        self.assertEqual(dashboard.ui_scale_for_display(1920, 1080), 1.0)
        self.assertGreater(dashboard.ui_scale_for_display(3840, 2160), 1.5)
        self.assertLessEqual(dashboard.ui_scale_for_display(7680, 4320), 1.65)

    def test_event_window_rejects_bad_and_expired_timestamps(self) -> None:
        now = datetime(2026, 7, 11, 12, tzinfo=UTC)
        self.assertTrue(dashboard.event_within_window("2026-07-11T11:00:00Z", "24h", now=now))
        self.assertFalse(dashboard.event_within_window("2026-07-10T11:00:00Z", "24h", now=now))
        self.assertFalse(dashboard.event_within_window("not-a-time", "7d", now=now))
        self.assertTrue(dashboard.event_within_window("not-a-time", "all", now=now))

    def test_parse_timestamp_accepts_utc_z_suffix(self) -> None:
        parsed = dashboard.parse_timestamp("2026-07-11T04:24:17Z")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.utcoffset().total_seconds(), 0)

    def test_session_details_supports_legacy_and_descriptive_sessions(self) -> None:
        legacy = dashboard.session_details("session-1", "2026-07-11T04:24:17Z")
        detailed = dashboard.session_details(
            "session-2",
            {
                "last_seen_at": "2026-07-11T04:24:17Z",
                "user_id": "local_user",
                "profile_name": "Local User",
                "device_id": "smai_client_0123456789abcdef",
                "connection_state": "connected",
            },
        )

        self.assertEqual(legacy["last_seen_at"], "2026-07-11T04:24:17Z")
        self.assertEqual(legacy["user_id"], "")
        self.assertEqual(detailed["user_id"], "local_user")
        self.assertEqual(detailed["profile_name"], "Local User")
        self.assertEqual(detailed["connection_state"], "connected")

    def test_health_score_is_fail_closed_for_unknown(self) -> None:
        self.assertEqual(dashboard.Dashboard._health_score("unknown"), 0)
        self.assertEqual(dashboard.Dashboard._health_score("healthy"), 100)

    def test_analytics_brand_assets_are_project_bound(self) -> None:
        self.assertTrue(dashboard.ANALYTICS_LOGO.is_file())
        self.assertTrue(dashboard.ANALYTICS_MASCOT.is_file())
        self.assertTrue(dashboard.ANALYTICS_WORDMARK.is_file())
        self.assertEqual(dashboard.ANALYTICS_LOGO.parent, dashboard.ASSET_ROOT)
        self.assertEqual(dashboard.ANALYTICS_MASCOT.parent, dashboard.ASSET_ROOT)
        self.assertEqual(dashboard.ANALYTICS_WORDMARK.parent, dashboard.ASSET_ROOT)

    def test_header_wordmark_is_an_alpha_png(self) -> None:
        # PNG IHDR color type 6 denotes RGBA, which keeps the header background transparent.
        for asset in (dashboard.ANALYTICS_LOGO, dashboard.ANALYTICS_WORDMARK):
            header = asset.read_bytes()[:26]
            self.assertEqual(header[:8], b"\x89PNG\r\n\x1a\n")
            self.assertEqual(header[25], 6)

    def test_topology_status_is_unknown_without_check_evidence(self) -> None:
        dashboard_like = SimpleNamespace(check_statuses={"streamlit health": "ok"})
        self.assertEqual(dashboard.Dashboard._service_status(dashboard_like, "smai ui"), "unknown")
        self.assertEqual(dashboard.Dashboard._service_status(dashboard_like, "streamlit"), "ok")

    def test_scheduled_task_path_mismatch_is_not_treated_as_ready(self) -> None:
        expected = str(dashboard.expected_task_root("SmartMarketAI-Server-Watch"))
        self.assertEqual(dashboard.task_path_status("SmartMarketAI-Server-Watch", f"<Command>{expected}</Command>"), "ready")
        self.assertEqual(
            dashboard.task_path_status("SmartMarketAI-Server-Watch", r"<Command>C:\Users\user\workspace\Smart_Market_AI\scripts\watch.bat</Command>"),
            "path mismatch",
        )

    def test_incident_automation_task_is_bound_to_analytics_project(self) -> None:
        self.assertEqual(
            dashboard.expected_task_root("SMAI-Incident-Automation"),
            dashboard.Path(__file__).resolve().parents[1],
        )

    def test_tree_status_tag_prioritizes_attention_states(self) -> None:
        self.assertEqual(dashboard.Dashboard._tree_status_tag("failed"), "critical")
        self.assertEqual(dashboard.Dashboard._tree_status_tag("stale"), "degraded")
        self.assertEqual(dashboard.Dashboard._tree_status_tag("ok"), "healthy")


if __name__ == "__main__":
    unittest.main()
