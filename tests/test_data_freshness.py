from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from smai_analytics.monitoring import data_freshness


class DataFreshnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.now = datetime(2026, 7, 19, tzinfo=UTC)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _write(self, policy: data_freshness.FreshnessPolicy, **status: object) -> None:
        path = self.root / policy.relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(status), encoding="utf-8")

    def test_collect_marks_recent_success_as_healthy(self) -> None:
        news, symbols = data_freshness.POLICIES
        self._write(news, last_success_at=self.now.isoformat(), consecutive_failures=0)
        self._write(symbols, last_success_at=self.now.isoformat(), last_exit_code=0)

        checks = data_freshness.collect_checks(self.root, now=self.now)

        self.assertEqual(["ok", "ok"], [check["status"] for check in checks])

    def test_collect_fails_closed_for_missing_or_malformed_state(self) -> None:
        checks = data_freshness.collect_checks(self.root, now=self.now)

        self.assertEqual(["unknown", "unknown"], [check["status"] for check in checks])

    def test_collect_reports_news_staleness_and_maintenance_failure(self) -> None:
        news, symbols = data_freshness.POLICIES
        self._write(
            news,
            last_success_at=(self.now - timedelta(hours=25)).isoformat(),
            consecutive_failures=0,
        )
        self._write(
            symbols,
            last_success_at=self.now.isoformat(),
            last_exit_code=1,
        )

        checks = data_freshness.collect_checks(self.root, now=self.now)

        self.assertEqual("degraded", checks[0]["status"])
        self.assertEqual("degraded", checks[1]["status"])

    def test_news_repeated_failures_are_critical(self) -> None:
        news, _symbols = data_freshness.POLICIES
        self._write(news, last_success_at=self.now.isoformat(), consecutive_failures=4)

        self.assertEqual("critical", data_freshness.collect_checks(self.root, now=self.now)[0]["status"])

    def test_symbol_maintenance_remains_healthy_inside_its_weekly_contract(self) -> None:
        _news, symbols = data_freshness.POLICIES
        self._write(
            symbols,
            last_success_at=(self.now - timedelta(days=7, hours=12)).isoformat(),
            last_exit_code=0,
        )

        check = data_freshness.collect_checks(self.root, now=self.now)[1]

        self.assertEqual("ok", check["status"])

    def test_symbol_health_uses_weekly_maintenance_not_optional_cache_refresh(self) -> None:
        _news, symbols = data_freshness.POLICIES
        self._write(symbols, last_success_at=(self.now - timedelta(days=3)).isoformat(), last_exit_code=0)
        cache = self.root / "data/cache/symbol_refresh_status.json"
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({"last_success_at": "2020-01-01", "consecutive_failures": 0}), encoding="utf-8")

        self.assertEqual("ok", data_freshness.collect_checks(self.root, now=self.now)[1]["status"])

    def test_symbol_maintenance_overdue_remains_critical(self) -> None:
        _news, symbols = data_freshness.POLICIES
        self._write(symbols, last_success_at=(self.now - timedelta(days=11)).isoformat(), last_exit_code=0)

        self.assertEqual("critical", data_freshness.collect_checks(self.root, now=self.now)[1]["status"])
