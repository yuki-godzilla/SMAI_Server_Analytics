import unittest
from datetime import UTC, datetime

import analytics_web


class AnalyticsWebFormattingTests(unittest.TestCase):
    def test_web_health_score_is_fail_closed(self) -> None:
        self.assertEqual(analytics_web.health_score("healthy"), 100)
        self.assertEqual(analytics_web.health_score("unknown"), 0)
        self.assertEqual(analytics_web.health_score(""), 0)

    def test_web_session_connection_needs_fresh_heartbeat(self) -> None:
        now = datetime(2026, 7, 13, 5, 0, tzinfo=UTC)
        self.assertEqual(
            analytics_web.session_connection_status(
                {"last_seen_at": "2026-07-13T04:59:30Z", "connection_state": "connected"},
                now=now,
            ),
            "ok",
        )
        self.assertEqual(
            analytics_web.session_connection_status(
                {"last_seen_at": "2026-07-13T04:55:00Z", "connection_state": "connected"},
                now=now,
            ),
            "degraded",
        )
        self.assertEqual(
            analytics_web.session_connection_status(
                {"last_seen_at": "2026-07-13T04:59:30Z", "connection_state": "failed"},
                now=now,
            ),
            "critical",
        )

    def test_web_service_status_stays_unknown_without_evidence(self) -> None:
        self.assertEqual(analytics_web.service_status({"streamlit health": "ok"}, "runtime"), "unknown")
        self.assertEqual(analytics_web.service_status({"streamlit health": "ok"}, "streamlit"), "ok")

    def test_web_assets_and_lan_launcher_are_project_bound(self) -> None:
        self.assertTrue(analytics_web.ANALYTICS_WORDMARK.is_file())
        self.assertTrue(analytics_web.ANALYTICS_MASCOT.is_file())
        launcher = analytics_web.Path(__file__).resolve().parents[1] / "run_analytics_web.bat"
        content = launcher.read_text(encoding="utf-8")
        self.assertIn("--server.address 0.0.0.0", content)
        self.assertIn("SMAI_ANALYTICS_PORT=8502", content)


if __name__ == "__main__":
    unittest.main()
