import unittest
from datetime import UTC, datetime, timedelta

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
        self.assertEqual(analytics_web.health_gauge_class("healthy"), "health-score-healthy")
        self.assertEqual(analytics_web.health_gauge_class("not-a-status"), "health-score-unknown")

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
        self.assertTrue(analytics_web.ANALYTICS_WORDMARK_LARGE_TEXT.is_file())
        self.assertTrue(analytics_web.ANALYTICS_MASCOT.is_file())
        self.assertTrue(analytics_web.ANALYTICS_MASCOT_HEADER.is_file())
        self.assertTrue(analytics_web.ANALYTICS_APP_ICON.is_file())
        self.assertTrue(analytics_web.TOPOLOGY_SPRITE.is_file())
        self.assertTrue(analytics_web.TOPOLOGY_SMARTPHONE.is_file())
        self.assertTrue(analytics_web.TOPOLOGY_TABLET.is_file())
        self.assertTrue(analytics_web._browser_app_icon().startswith(b"\x89PNG"))
        launcher = analytics_web.Path(__file__).resolve().parents[1] / "run_analytics_web.bat"
        content = launcher.read_text(encoding="utf-8")
        self.assertIn("--server.address 0.0.0.0", content)
        self.assertIn("SMAI_ANALYTICS_PORT=8502", content)

    def test_web_tab_contract_covers_every_operations_surface(self) -> None:
        self.assertEqual(
            analytics_web.WEB_TAB_LABELS,
            ("DashBoard", "推移", "セッション", "操作履歴", "障害", "改善レポート", "タスク", "ログ"),
        )

    def test_overview_next_check_keeps_unknown_and_critical_fail_closed(self) -> None:
        self.assertEqual(analytics_web._next_check({"overall": "unknown"})[0], "推移")
        self.assertEqual(analytics_web._next_check({"overall": "critical"})[0], "障害")

    def test_overview_next_check_does_not_treat_missing_tasks_as_a_task_failure(self) -> None:
        self.assertEqual(analytics_web._next_check({"overall": "healthy", "tasks": []})[0], "DashBoard")
        self.assertEqual(
            analytics_web._next_check(
                {"overall": "healthy", "tasks": [{"status": "degraded"}]}
            )[0],
            "タスク",
        )

    def test_dashboard_connection_nodes_animate_only_current_heartbeats(self) -> None:
        now = datetime.now(UTC).isoformat()
        available, nodes = analytics_web._dashboard_connection_nodes(
            {
                "activity_available": True,
                "sessions": [
                    {"client_type": "desktop", "last_seen_at": now, "connection_state": "connected"},
                    {"client_type": "smartphone", "last_seen_at": now, "connection_state": "connected"},
                    {"client_type": "tablet", "last_seen_at": now, "connection_state": "closed"},
                ],
            }
        )
        by_client = {str(node["client"]): node for node in nodes}

        self.assertTrue(available)
        self.assertTrue(by_client["desktop"]["flow"])
        self.assertTrue(by_client["smartphone"]["flow"])
        self.assertFalse(by_client["tablet"]["flow"])
        self.assertEqual(by_client["tablet"]["status"], "degraded")

    def test_live_connection_map_uses_bidirectional_particles_only_for_current_heartbeats(self) -> None:
        class MarkdownRecorder:
            rendered = ""

            @staticmethod
            def markdown(value: str, **_: object) -> None:
                MarkdownRecorder.rendered = value

        now = datetime.now(UTC).isoformat()
        original_streamlit = analytics_web.st
        analytics_web.st = MarkdownRecorder
        try:
            analytics_web._render_live_connection_map(
                {
                    "activity_available": True,
                    "overall": "healthy",
                    "sessions": [
                        {"client_type": "desktop", "last_seen_at": now, "connection_state": "connected"},
                        {"client_type": "smartphone", "last_seen_at": now, "connection_state": "closed"},
                    ],
                }
            )
        finally:
            analytics_web.st = original_streamlit

        self.assertIn("LIVE HEARTBEAT FLOW", MarkdownRecorder.rendered)
        self.assertIn("network-link-flow-halo", MarkdownRecorder.rendered)
        self.assertIn("network-packet-return", MarkdownRecorder.rendered)
        self.assertIn('viewBox="0 0 1000 528"', MarkdownRecorder.rendered)
        self.assertIn('path="M 160 403 C 262 276 436 190 500 134"', MarkdownRecorder.rendered)
        self.assertEqual(1, MarkdownRecorder.rendered.count('class="network-link network-link-active"'))

    def test_dashboard_health_points_keep_unknown_at_zero(self) -> None:
        now = datetime.now(UTC).replace(microsecond=0)
        points = analytics_web._dashboard_health_points(
            {
                "rollups": [
                    {"bucket_start": (now - timedelta(minutes=5)).isoformat(), "overall": {"healthy": 1}},
                    {"bucket_start": now.isoformat(), "overall": {"unknown": 1}},
                ]
            }
        )

        self.assertEqual([100.0, 0.0], [value for _, value in points])

    def test_health_history_uses_an_area_fill_without_changing_other_sparklines(self) -> None:
        now = datetime.now(UTC)
        health_chart = analytics_web._sparkline_svg(
            [(now - timedelta(minutes=5), 100.0), (now, 100.0)],
            color="#34D399",
            label="Health",
            upper=100.0,
            area=True,
        )
        latency_chart = analytics_web._sparkline_svg(
            [(now - timedelta(minutes=5), 15.0), (now, 18.0)],
            color="#A78BFA",
            label="Latency",
        )

        self.assertIn('class="spark-area"', health_chart)
        self.assertNotIn('class="spark-area"', latency_chart)

    def test_health_timeline_groups_heading_with_chart_for_equal_blocks(self) -> None:
        class MarkdownRecorder:
            rendered = ""

            @staticmethod
            def markdown(value: str, **_: object) -> None:
                MarkdownRecorder.rendered = value

        original_streamlit = analytics_web.st
        analytics_web.st = MarkdownRecorder
        try:
            analytics_web._render_health_timeline({"overall": "healthy", "rollups": []})
        finally:
            analytics_web.st = original_streamlit

        self.assertIn('class="health-history-block"><div class="visual-heading">', MarkdownRecorder.rendered)
        self.assertIn('</div></div><div class="health-micro-block"><div class="micro-trend-grid">', MarkdownRecorder.rendered)

    def test_narrow_health_timeline_reserves_equal_height_for_both_blocks(self) -> None:
        class MarkdownRecorder:
            rendered = ""

            @staticmethod
            def markdown(value: str, **_: object) -> None:
                MarkdownRecorder.rendered = value

        original_streamlit = analytics_web.st
        analytics_web.st = MarkdownRecorder
        try:
            analytics_web._render_styles()
        finally:
            analytics_web.st = original_streamlit

        self.assertIn('.health-visual-surface { height: 560px; min-height: 560px; }', MarkdownRecorder.rendered)
        self.assertIn('.health-history-block, .health-micro-block { min-height: 0; }', MarkdownRecorder.rendered)


if __name__ == "__main__":
    unittest.main()
