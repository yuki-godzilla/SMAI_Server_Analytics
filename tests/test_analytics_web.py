import unittest
from datetime import UTC, datetime

import analytics_web


class AnalyticsWebFormattingTests(unittest.TestCase):
    def test_current_check_summary_marks_failures_and_unknowns_for_attention(self) -> None:
        level, message = analytics_web._check_attention_summary(
            {"checks": [{"status": "failed"}, {"status": "unknown"}, {"status": "ok"}]}
        ) or (None, "")

        self.assertEqual("error", level)
        self.assertIn("失敗・重大 1件", message)
        self.assertIn("不明 1件", message)

    def test_current_check_summary_omits_only_healthy_evidence(self) -> None:
        self.assertIsNone(analytics_web._check_attention_summary({"checks": [{"status": "ok"}, {"status": "healthy"}]}))

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
        self.assertTrue(analytics_web.ANALYTICS_MASCOT_HEADER.is_file())
        self.assertTrue(analytics_web.ANALYTICS_APP_ICON.is_file())
        launcher = analytics_web.Path(__file__).resolve().parents[1] / "run_analytics_web.bat"
        content = launcher.read_text(encoding="utf-8")
        self.assertIn("--server.address 0.0.0.0", content)
        self.assertIn("SMAI_ANALYTICS_PORT=8502", content)

    def test_web_tab_contract_covers_every_operations_surface(self) -> None:
        self.assertEqual(
            analytics_web.WEB_TAB_LABELS,
            ("概要", "推移", "セッション", "操作履歴", "障害", "改善レポート", "タスク", "ログ"),
        )

    def test_overview_next_check_keeps_unknown_and_critical_fail_closed(self) -> None:
        self.assertEqual(analytics_web._next_check({"overall": "unknown"})[0], "推移")
        self.assertEqual(analytics_web._next_check({"overall": "critical"})[0], "障害")

    def test_overview_next_check_does_not_treat_missing_tasks_as_a_task_failure(self) -> None:
        self.assertEqual(analytics_web._next_check({"overall": "healthy", "tasks": []})[0], "概要")
        self.assertEqual(
            analytics_web._next_check(
                {"overall": "healthy", "tasks": [{"status": "degraded"}]}
            )[0],
            "タスク",
        )


if __name__ == "__main__":
    unittest.main()
