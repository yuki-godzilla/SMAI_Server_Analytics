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

    def test_japanese_filter_labels_preserve_stable_storage_keys(self) -> None:
        self.assertEqual(dashboard.time_window_key("過去24時間"), "24h")
        self.assertEqual(dashboard.time_window_key("すべて"), "all")
        self.assertEqual(dashboard.result_filter_key("失敗"), "failed")
        self.assertEqual(dashboard.result_filter_key("重大"), "critical")

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
                "client_type": "smartphone",
                "connection_state": "connected",
            },
        )

        self.assertEqual(legacy["last_seen_at"], "2026-07-11T04:24:17Z")
        self.assertEqual(legacy["user_id"], "")
        self.assertEqual(detailed["user_id"], "local_user")
        self.assertEqual(detailed["profile_name"], "Local User")
        self.assertEqual(detailed["client_type"], "smartphone")
        self.assertEqual(detailed["connection_state"], "connected")

    def test_client_connection_status_needs_category_specific_heartbeat_evidence(self) -> None:
        now = datetime(2026, 7, 12, 9, 0, tzinfo=UTC)
        sessions = [
            {
                "client_type": "smartphone",
                "last_seen_at": "2026-07-12T08:59:20+00:00",
                "connection_state": "connected",
            },
            {
                "client_type": "tablet",
                "last_seen_at": "2026-07-12T08:55:00+00:00",
                "connection_state": "connected",
            },
        ]

        self.assertEqual(
            dashboard.client_connection_status(sessions, "smartphone", activity_readable=True, now=now),
            "ok",
        )
        self.assertEqual(
            dashboard.client_connection_status(sessions, "tablet", activity_readable=True, now=now),
            "degraded",
        )
        self.assertEqual(
            dashboard.client_connection_status(sessions, "desktop", activity_readable=True, now=now),
            "unknown",
        )
        self.assertEqual(
            dashboard.client_connection_status(sessions, "smartphone", activity_readable=False, now=now),
            "unknown",
        )

    def test_explicit_client_communication_failure_is_critical(self) -> None:
        session = {
            "client_type": "tablet",
            "last_seen_at": "2026-07-12T08:59:59+00:00",
            "connection_state": "failed",
        }

        self.assertEqual(
            dashboard.session_connection_status(session, now=datetime(2026, 7, 12, 9, 0, tzinfo=UTC)),
            "critical",
        )

    def test_health_score_is_fail_closed_for_unknown(self) -> None:
        self.assertEqual(dashboard.Dashboard._health_score("unknown"), 0)
        self.assertEqual(dashboard.Dashboard._health_score("healthy"), 100)

    def test_analytics_brand_assets_are_project_bound(self) -> None:
        self.assertTrue(dashboard.ANALYTICS_LOGO.is_file())
        self.assertTrue(dashboard.ANALYTICS_MASCOT.is_file())
        self.assertTrue(dashboard.ANALYTICS_WORDMARK.is_file())
        self.assertTrue(dashboard.TOPOLOGY_SMARTPHONE.is_file())
        self.assertTrue(dashboard.TOPOLOGY_TABLET.is_file())
        self.assertEqual(dashboard.ANALYTICS_LOGO.parent, dashboard.ASSET_ROOT)
        self.assertEqual(dashboard.ANALYTICS_MASCOT.parent, dashboard.ASSET_ROOT)
        self.assertEqual(dashboard.ANALYTICS_WORDMARK.parent, dashboard.ASSET_ROOT)

    def test_header_wordmark_is_an_alpha_png(self) -> None:
        # PNG IHDR color type 6 denotes RGBA, which keeps the header background transparent.
        for asset in (
            dashboard.ANALYTICS_LOGO,
            dashboard.ANALYTICS_WORDMARK,
            dashboard.TOPOLOGY_SMARTPHONE,
            dashboard.TOPOLOGY_TABLET,
        ):
            header = asset.read_bytes()[:26]
            self.assertEqual(header[:8], b"\x89PNG\r\n\x1a\n")
            self.assertEqual(header[25], 6)


    @unittest.skipIf(dashboard.Image is None, "Pillow is optional at runtime")
    def test_topology_client_assets_have_transparent_corners(self) -> None:
        for asset in (dashboard.TOPOLOGY_SMARTPHONE, dashboard.TOPOLOGY_TABLET):
            with dashboard.Image.open(asset) as image:
                self.assertEqual(image.convert("RGBA").getpixel((0, 0))[3], 0)

    @unittest.skipIf(dashboard.Image is None, "Pillow is optional at runtime")
    def test_wordmark_split_uses_the_transparent_gap_between_shield_and_text(self) -> None:
        with dashboard.Image.open(dashboard.ANALYTICS_WORDMARK) as source:
            split = dashboard.Dashboard._wordmark_split(source.convert("RGBA"))

        self.assertIsNotNone(split)
        self.assertGreater(split, 574)
        self.assertLess(split, 599)

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
