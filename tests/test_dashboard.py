import unittest
from types import SimpleNamespace

import dashboard


class DashboardFormattingTests(unittest.TestCase):
    def test_compact_id_keeps_short_value(self) -> None:
        self.assertEqual(dashboard.compact_id("session-1"), "session-1")

    def test_compact_id_shortens_long_value(self) -> None:
        self.assertEqual(dashboard.compact_id("1234567890abcdefghijklmnop"), "12345678…klmnop")

    def test_parse_timestamp_accepts_utc_z_suffix(self) -> None:
        parsed = dashboard.parse_timestamp("2026-07-11T04:24:17Z")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.utcoffset().total_seconds(), 0)

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

    def test_tree_status_tag_prioritizes_attention_states(self) -> None:
        self.assertEqual(dashboard.Dashboard._tree_status_tag("failed"), "critical")
        self.assertEqual(dashboard.Dashboard._tree_status_tag("stale"), "degraded")
        self.assertEqual(dashboard.Dashboard._tree_status_tag("ok"), "healthy")


if __name__ == "__main__":
    unittest.main()
