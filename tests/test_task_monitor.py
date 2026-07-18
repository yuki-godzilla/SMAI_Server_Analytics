import subprocess
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest import mock

import task_monitor

LIST_OUTPUT = """\
Status:                               Ready
Last Run Time:                        2026/07/12 09:02:39
Last Result:                          0
Next Run Time:                        N/A
Scheduled Task State:                 Enabled
"""


class TaskMonitorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="smai-task-monitor-")
        self.runtime = Path(self.temp_dir.name) / "runtime"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_scheduler_values_reads_only_required_metadata(self) -> None:
        values = task_monitor.scheduler_values(LIST_OUTPUT)
        self.assertEqual(values["status"], "Ready")
        self.assertEqual(values["last_result"], "0")
        self.assertEqual(values["last_run_time"], "2026/07/12 09:02:39")

    def test_incident_task_staleness_is_degraded_then_critical(self) -> None:
        now = datetime(2026, 7, 12, 12, tzinfo=UTC)
        recent = {"last_result": "0", "last_run_time": (now - timedelta(minutes=8)).isoformat()}
        degraded = {"last_result": "0", "last_run_time": (now - timedelta(minutes=12)).isoformat()}
        critical = {"last_result": "0", "last_run_time": (now - timedelta(minutes=21)).isoformat()}
        self.assertEqual(task_monitor.classify_task("SMAI-Incident-Automation", recent, path_ok=True, now=now)[0], "healthy")
        self.assertEqual(task_monitor.classify_task("SMAI-Incident-Automation", degraded, path_ok=True, now=now)[0], "degraded")
        self.assertEqual(task_monitor.classify_task("SMAI-Incident-Automation", critical, path_ok=True, now=now)[0], "critical")

    def test_autofix_deploy_executor_has_a_short_freshness_window(self) -> None:
        now = datetime(2026, 7, 12, 12, tzinfo=UTC)
        recent = {"last_result": "0", "last_run_time": (now - timedelta(minutes=2)).isoformat()}
        degraded = {"last_result": "0", "last_run_time": (now - timedelta(minutes=4)).isoformat()}
        critical = {"last_result": "0", "last_run_time": (now - timedelta(minutes=6)).isoformat()}
        self.assertEqual(task_monitor.classify_task("SMAI-Codex-Autofix-Deploy", recent, path_ok=True, now=now)[0], "healthy")
        self.assertEqual(task_monitor.classify_task("SMAI-Codex-Autofix-Deploy", degraded, path_ok=True, now=now)[0], "degraded")
        self.assertEqual(task_monitor.classify_task("SMAI-Codex-Autofix-Deploy", critical, path_ok=True, now=now)[0], "critical")

    def test_daily_runtime_retention_has_a_daily_freshness_window(self) -> None:
        now = datetime(2026, 7, 12, 12, tzinfo=UTC)
        recent = {"last_result": "0", "last_run_time": (now - timedelta(hours=25)).isoformat()}
        stale = {"last_result": "0", "last_run_time": (now - timedelta(hours=49)).isoformat()}
        self.assertEqual(task_monitor.classify_task("SMAI-Runtime-Retention", recent, path_ok=True, now=now)[0], "healthy")
        self.assertEqual(task_monitor.classify_task("SMAI-Runtime-Retention", stale, path_ok=True, now=now)[0], "critical")

    def test_nonzero_result_and_path_mismatch_are_not_ready(self) -> None:
        now = datetime(2026, 7, 12, 12, tzinfo=UTC)
        values = {"last_result": "1", "last_run_time": now.isoformat()}
        self.assertEqual(task_monitor.classify_task("SmartMarketAI-Server-Watch", values, path_ok=True, now=now)[0], "critical")
        status, detail = task_monitor.classify_task("SmartMarketAI-Server-Watch", values, path_ok=False, now=now)
        self.assertEqual(status, "critical")
        self.assertIn("実行パス", detail)
        self.assertEqual(task_monitor.classify_task("SmartMarketAI-Server-Watch", {"last_result": "0"}, path_ok=False, now=now)[0], "degraded")

    def test_scheduler_informational_states_are_not_process_failures(self) -> None:
        now = datetime(2026, 7, 12, 12, tzinfo=UTC)

        self.assertEqual(
            task_monitor.classify_task("SmartMarketAI-Server-Autostart", {"last_result": str(0x41301)}, path_ok=True, now=now),
            ("healthy", "タスクは実行中です"),
        )
        self.assertEqual(
            task_monitor.classify_task("SMAI-Host-Maintenance", {"last_result": str(0x41303)}, path_ok=True, now=now),
            ("unknown", "タスクは登録済みですが、まだ実行履歴がありません"),
        )
        self.assertEqual(
            task_monitor.classify_task("SmartMarketAI-Server-Autostart", {"last_result": str(0x41301)}, path_ok=False, now=now)[0],
            "degraded",
        )

    def test_backup_smoke_age_and_missing_state_fail_closed(self) -> None:
        now = datetime(2026, 7, 12, 12, tzinfo=UTC)
        self.assertEqual(task_monitor.backup_row({}, now=now)["status"], "unknown")
        stale = {"overall": "healthy", "checked_at": (now - timedelta(days=36)).isoformat()}
        self.assertEqual(task_monitor.backup_row(stale, now=now)["status"], "critical")

    def test_records_changes_and_reads_history(self) -> None:
        now = datetime(2026, 7, 12, 12, tzinfo=UTC)
        healthy = [{"name": "SMAI-Incident-Automation", "status": "healthy", "last_run_at": now.isoformat(), "detail": "予定内", "source": "scheduler"}]
        changed = [{"name": "SMAI-Incident-Automation", "status": "critical", "last_run_at": now.isoformat(), "detail": "期限超過", "source": "scheduler"}]
        self.assertTrue(task_monitor.record_observation(healthy, self.runtime, now=now))
        self.assertTrue(task_monitor.record_observation(healthy, self.runtime, now=now + timedelta(minutes=1)))
        self.assertTrue(task_monitor.record_observation(changed, self.runtime, now=now + timedelta(minutes=2)))
        rows = task_monitor.read_observations(self.runtime, now=now + timedelta(minutes=3), window=timedelta(minutes=10))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[-1]["tasks"][0]["status"], "critical")

    def test_query_task_verifies_xml_workspace_path(self) -> None:
        def runner(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            if "/XML" in command:
                return subprocess.CompletedProcess(command, 0, "<Command>C:\\workspace\\current\\run.bat</Command>", "")
            return subprocess.CompletedProcess(command, 0, LIST_OUTPUT, "")

        row = task_monitor.query_task(
            "SMAI-Server-Analytics",
            expected_root=Path(r"C:\workspace\current"),
            runner=runner,
            now=datetime(2026, 7, 12, 12, tzinfo=UTC),
        )
        self.assertEqual(row["status"], "healthy")
        self.assertEqual(row["last_result"], "0")

    def test_query_task_accepts_resolved_junction_workspace_path(self) -> None:
        def runner(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            if "/XML" in command:
                return subprocess.CompletedProcess(command, 0, "<WorkingDirectory>C:\\workspace\\physical</WorkingDirectory>", "")
            return subprocess.CompletedProcess(command, 0, LIST_OUTPUT, "")

        with mock.patch("task_monitor.Path.resolve", return_value=Path(r"C:\workspace\physical")):
            row = task_monitor.query_task(
                "SMAI-Server-Analytics",
                expected_root=Path(r"C:\workspace\alias"),
                runner=runner,
                now=datetime(2026, 7, 12, 12, tzinfo=UTC),
            )

        self.assertEqual(row["status"], "healthy")


if __name__ == "__main__":
    unittest.main()
