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
        for policy in data_freshness.POLICIES:
            self._write(policy, last_success_at=self.now.isoformat(), consecutive_failures=0)

        checks = data_freshness.collect_checks(self.root, now=self.now)

        self.assertEqual(["ok", "ok"], [check["status"] for check in checks])

    def test_collect_fails_closed_for_missing_or_malformed_state(self) -> None:
        checks = data_freshness.collect_checks(self.root, now=self.now)

        self.assertEqual(["unknown", "unknown"], [check["status"] for check in checks])

    def test_collect_escalates_stale_and_repeated_failures(self) -> None:
        news, symbols = data_freshness.POLICIES
        self._write(
            news,
            last_success_at=(self.now - timedelta(hours=25)).isoformat(),
            consecutive_failures=0,
        )
        self._write(
            symbols,
            last_success_at=self.now.isoformat(),
            consecutive_failures=4,
        )

        checks = data_freshness.collect_checks(self.root, now=self.now)

        self.assertEqual("degraded", checks[0]["status"])
        self.assertEqual("critical", checks[1]["status"])
