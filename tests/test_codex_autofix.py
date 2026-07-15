from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from smai_analytics.operations import codex_autofix


class CodexAutofixTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="smai-autofix-", dir=str(Path.cwd()))
        self.root = Path(self.temp_dir.name)
        self.repository = self.root / "repository"
        self.runtime = self.root / "runtime"
        self.repository.mkdir()
        self._git("init")
        (self.repository / "README.md").write_text("# Analytics\n", encoding="utf-8")
        (self.repository / "AGENTS.md").write_text("# Test instructions\n", encoding="utf-8")
        self._git("add", "--", "README.md", "AGENTS.md")
        self._git(
            "-c",
            "user.name=Autofix Test",
            "-c",
            "user.email=autofix@example.com",
            "commit",
            "-m",
            "initial",
        )
        incident_root = self.runtime / "incident_operations"
        self.paths = {
            "REPOSITORY_ROOT": codex_autofix.REPOSITORY_ROOT,
            "RUNTIME_ROOT": codex_autofix.RUNTIME_ROOT,
            "INCIDENT_ROOT": codex_autofix.INCIDENT_ROOT,
            "REQUESTS_DIR": codex_autofix.REQUESTS_DIR,
            "REPORTS_DIR": codex_autofix.REPORTS_DIR,
            "AUTOFIX_ROOT": codex_autofix.AUTOFIX_ROOT,
            "AUTOFIX_STATE_DIR": codex_autofix.AUTOFIX_STATE_DIR,
            "AUTOFIX_RUNS_DIR": codex_autofix.AUTOFIX_RUNS_DIR,
            "AUTOFIX_WORKTREES_DIR": codex_autofix.AUTOFIX_WORKTREES_DIR,
            "AUTOFIX_INDEX_PATH": codex_autofix.AUTOFIX_INDEX_PATH,
            "AUTOFIX_LOCK_PATH": codex_autofix.AUTOFIX_LOCK_PATH,
            "AUTOFIX_CONFIG_PATH": codex_autofix.AUTOFIX_CONFIG_PATH,
        }
        codex_autofix.REPOSITORY_ROOT = self.repository
        codex_autofix.RUNTIME_ROOT = self.runtime
        codex_autofix.INCIDENT_ROOT = incident_root
        codex_autofix.REQUESTS_DIR = incident_root / "codex_requests"
        codex_autofix.REPORTS_DIR = incident_root / "reports"
        codex_autofix.AUTOFIX_ROOT = incident_root / "autofix"
        codex_autofix.AUTOFIX_STATE_DIR = codex_autofix.AUTOFIX_ROOT / "states"
        codex_autofix.AUTOFIX_RUNS_DIR = codex_autofix.AUTOFIX_ROOT / "runs"
        codex_autofix.AUTOFIX_WORKTREES_DIR = codex_autofix.AUTOFIX_ROOT / "worktrees"
        codex_autofix.AUTOFIX_INDEX_PATH = codex_autofix.AUTOFIX_ROOT / "events.jsonl"
        codex_autofix.AUTOFIX_LOCK_PATH = codex_autofix.AUTOFIX_ROOT / "worker.lock"
        codex_autofix.AUTOFIX_CONFIG_PATH = self.root / "codex_autofix.json"
        self.report_patch = patch(
            "smai_analytics.operations.incident_automation.record_improvement_report"
        )
        self.report_mock = self.report_patch.start()

    def tearDown(self) -> None:
        self.report_patch.stop()
        for name, value in self.paths.items():
            setattr(codex_autofix, name, value)
        self.temp_dir.cleanup()

    def _git(self, *args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=self.repository,
            text=True,
            capture_output=True,
            check=True,
        )
        return result.stdout.strip()

    def _request(self, request_id: str = "incident-test") -> None:
        codex_autofix.REQUESTS_DIR.mkdir(parents=True, exist_ok=True)
        codex_autofix.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        (codex_autofix.REQUESTS_DIR / f"{request_id}.md").write_text(
            "# Request\n\n- Severity: `critical`\n- Evidence: Streamlit health\n",
            encoding="utf-8",
        )
        (codex_autofix.REPORTS_DIR / f"{request_id}.md").write_text(
            "# Report\n",
            encoding="utf-8",
        )

    def _prepare_ready_patch(self) -> tuple[datetime, dict[str, object]]:
        self._request()
        started = datetime.now(UTC)
        approved = codex_autofix.approve_autofix(
            request_id="incident-test",
            now=started,
            repository=self.repository,
        )

        def fake_codex_runner(
            worktree: Path,
            current: object,
            schema_path: Path,
            result_path: Path,
        ) -> int:
            del current, schema_path
            with (worktree / "README.md").open("a", encoding="utf-8", newline="") as stream:
                stream.write("Autofix verified repair.\n")
            result_path.write_text(
                json.dumps(
                    {
                        "request_id": "incident-test",
                        "base_commit": approved["base_commit"],
                        "status": "fixed",
                        "summary": "Updated the bounded Analytics documentation.",
                        "changed_files": ["README.md"],
                        "verification": ["synthetic validator"],
                        "needs_operator_visual_review": False,
                    }
                ),
                encoding="utf-8",
            )
            return 0

        repaired = codex_autofix.execute_repair(
            codex_autofix._load_json(codex_autofix._state_path("incident-test")),
            repository=self.repository,
            now=started + timedelta(minutes=1),
            codex_runner=fake_codex_runner,
            validator=lambda _path, _base: ["synthetic validator passed"],
        )
        self.assertEqual("auto_patch_ready", repaired["status"], repaired)
        return started, repaired

    def _prepare_merged_patch(
        self,
    ) -> tuple[datetime, dict[str, object], dict[str, object]]:
        started, repaired = self._prepare_ready_patch()
        codex_autofix.approve_autofix_merge(
            request_id="incident-test",
            commit=str(repaired["repair_commit"]),
            now=started + timedelta(minutes=2),
        )
        merged = codex_autofix.execute_merge(
            codex_autofix._load_json(codex_autofix._state_path("incident-test")),
            repository=self.repository,
            now=started + timedelta(minutes=3),
            validator=lambda _path, _base: ["post-merge validator passed"],
        )
        self.assertEqual("auto_merged_pending_deploy", merged["status"], merged)
        return started, repaired, merged

    def test_path_allowlist_is_fail_closed(self) -> None:
        for allowed in (
            "analytics_web.py",
            "README.md",
            "smai_analytics/operations/incident_automation.py",
            "tests/test_codex_autofix.py",
            "Documents/10_Codex_Autofix_Design.md",
        ):
            self.assertTrue(codex_autofix.path_is_allowed(allowed), allowed)
        for denied in (
            "scripts/register_task.ps1",
            "config/network.json",
            "pyproject.toml",
            "AGENTS.md",
            "../Smart_Market_AI/app.py",
            "smai_analytics/secret_store.py",
        ):
            self.assertFalse(codex_autofix.path_is_allowed(denied), denied)

    def test_result_schema_and_sensitive_diff_are_fail_closed(self) -> None:
        valid = {
            "request_id": "incident-test",
            "base_commit": "a" * 40,
            "status": "fixed",
            "summary": "bounded repair",
            "changed_files": ["README.md"],
            "verification": ["test passed"],
            "needs_operator_visual_review": False,
        }
        codex_autofix._validate_result(
            valid,
            request_id="incident-test",
            base_commit="a" * 40,
        )
        with self.assertRaises(codex_autofix.AutofixError) as context:
            codex_autofix._validate_result(
                {**valid, "unexpected": "field"},
                request_id="incident-test",
                base_commit="a" * 40,
            )
        self.assertEqual("result_schema", context.exception.category)
        with self.assertRaises(codex_autofix.AutofixError) as context:
            codex_autofix.validate_diff_text("+ api_key=sk_example_sensitive_value")
        self.assertEqual("sensitive_diff", context.exception.category)
        with self.assertRaises(codex_autofix.AutofixError) as context:
            codex_autofix.validate_diff_text("+ See https://external.example/repair")
        self.assertEqual("external_url_diff", context.exception.category)
        codex_autofix.validate_diff_text('+ Probe "http://localhost:8502"')

    def test_administrator_report_failure_does_not_change_a_completed_outcome(self) -> None:
        state: dict[str, object] = {
            "request_id": "incident-test",
            "status": "auto_applied",
        }
        codex_autofix._save_state(state, event="auto_applied")
        self.report_mock.side_effect = OSError("synthetic report failure")
        codex_autofix._append_report_event(
            state,
            status="auto_applied",
            summary="applied",
            verification="health passed",
            notification_kind="autofix_applied",
        )
        persisted = codex_autofix._load_json(codex_autofix._state_path("incident-test"))
        self.assertEqual("auto_applied", persisted["status"])
        self.assertEqual("administrator_report_failed", persisted["notification_failure_category"])

    def test_configuration_defaults_to_disabled_dry_run(self) -> None:
        self.assertEqual(
            {"enabled": False, "mode": "dry_run"},
            {key: codex_autofix.load_config()[key] for key in ("enabled", "mode")},
        )
        self.assertFalse(codex_autofix.load_config()["deployment_enabled"])
        codex_autofix.AUTOFIX_CONFIG_PATH.write_text(
            json.dumps({"enabled": True, "mode": "active"}),
            encoding="utf-8",
        )
        self.assertTrue(codex_autofix.load_config()["enabled"])

    def test_third_approval_requires_the_exact_merged_commit(self) -> None:
        started, repaired, _merged = self._prepare_merged_patch()
        with self.assertRaises(codex_autofix.AutofixError) as context:
            codex_autofix.approve_autofix_deploy(
                request_id="incident-test",
                commit="f" * 40,
                now=started + timedelta(minutes=4),
            )
        self.assertEqual("commit_mismatch", context.exception.category)
        approved = codex_autofix.approve_autofix_deploy(
            request_id="incident-test",
            commit=str(repaired["repair_commit"]),
            now=started + timedelta(minutes=4),
        )
        self.assertEqual("autofix_deploy_approved", approved["status"])

    def test_deployment_applies_after_preflight_backup_restart_and_health(self) -> None:
        started, repaired, _merged = self._prepare_merged_patch()
        codex_autofix.approve_autofix_deploy(
            request_id="incident-test",
            commit=str(repaired["repair_commit"]),
            now=started + timedelta(minutes=4),
        )
        restarts: list[str] = []
        result = codex_autofix.execute_deployment(
            codex_autofix._load_json(codex_autofix._state_path("incident-test")),
            repository=self.repository,
            now=started + timedelta(minutes=5),
            preflight_checker=lambda _now: [],
            backup_runner=lambda: "smai_test_backup",
            validator=lambda _path, _base: ["deploy validator passed"],
            restart_runner=lambda: restarts.append("restart"),
            health_verifier=lambda: ["health ok", "page ok"],
        )
        self.assertEqual("auto_applied", result["status"], result)
        self.assertEqual("smai_test_backup", result["backup_id"])
        self.assertEqual(["restart"], restarts)
        self.assertEqual(repaired["repair_commit"], self._git("rev-parse", "HEAD"))

    def test_deployment_preflight_blocks_active_sessions_before_restart(self) -> None:
        started, repaired, _merged = self._prepare_merged_patch()
        codex_autofix.approve_autofix_deploy(
            request_id="incident-test",
            commit=str(repaired["repair_commit"]),
            now=started + timedelta(minutes=4),
        )
        restarts: list[str] = []
        result = codex_autofix.execute_deployment(
            codex_autofix._load_json(codex_autofix._state_path("incident-test")),
            repository=self.repository,
            now=started + timedelta(minutes=5),
            preflight_checker=lambda _now: ["active_sessions"],
            backup_runner=lambda: "must_not_run",
            validator=lambda _path, _base: ["must not run"],
            restart_runner=lambda: restarts.append("restart"),
            health_verifier=lambda: ["must not run"],
        )
        self.assertEqual("auto_deploy_blocked", result["status"])
        self.assertEqual("preflight_active_sessions", result["failure_category"])
        self.assertEqual([], restarts)

    def test_failed_health_verification_creates_revert_commit_and_recovers(self) -> None:
        started, repaired, _merged = self._prepare_merged_patch()
        codex_autofix.approve_autofix_deploy(
            request_id="incident-test",
            commit=str(repaired["repair_commit"]),
            now=started + timedelta(minutes=4),
        )
        health_attempts = 0
        restarts: list[str] = []

        def verify_health() -> list[str]:
            nonlocal health_attempts
            health_attempts += 1
            if health_attempts == 1:
                raise codex_autofix.AutofixError("synthetic_health_failure", "failed")
            return ["rollback health recovered"]

        result = codex_autofix.execute_deployment(
            codex_autofix._load_json(codex_autofix._state_path("incident-test")),
            repository=self.repository,
            now=started + timedelta(minutes=5),
            preflight_checker=lambda _now: [],
            backup_runner=lambda: "smai_test_backup",
            validator=lambda _path, _base: ["deploy validator passed"],
            restart_runner=lambda: restarts.append("restart"),
            health_verifier=verify_health,
        )
        self.assertEqual("auto_rolled_back", result["status"], result)
        self.assertRegex(str(result["rollback_commit"]), r"^[0-9a-f]{40}$")
        self.assertEqual(2, len(restarts))
        self.assertNotEqual(repaired["repair_commit"], self._git("rev-parse", "HEAD"))
        self.assertNotIn(
            "Autofix verified repair",
            (self.repository / "README.md").read_text(encoding="utf-8"),
        )

    def test_rollback_failure_is_reported_as_critical_manual_recovery(self) -> None:
        started, repaired, _merged = self._prepare_merged_patch()
        codex_autofix.approve_autofix_deploy(
            request_id="incident-test",
            commit=str(repaired["repair_commit"]),
            now=started + timedelta(minutes=4),
        )

        def failed_restart() -> None:
            raise codex_autofix.AutofixError("synthetic_restart_failure", "failed")

        result = codex_autofix.execute_deployment(
            codex_autofix._load_json(codex_autofix._state_path("incident-test")),
            repository=self.repository,
            now=started + timedelta(minutes=5),
            preflight_checker=lambda _now: [],
            backup_runner=lambda: "smai_test_backup",
            validator=lambda _path, _base: ["deploy validator passed"],
            restart_runner=failed_restart,
            health_verifier=lambda: ["must not run"],
        )
        self.assertEqual("auto_rollback_failed", result["status"], result)
        self.assertEqual("synthetic_restart_failure", result["failure_category"])

    def test_deployment_worker_dry_run_does_not_restart(self) -> None:
        started, repaired, _merged = self._prepare_merged_patch()
        codex_autofix.approve_autofix_deploy(
            request_id="incident-test",
            commit=str(repaired["repair_commit"]),
            now=started + timedelta(minutes=4),
        )
        result = codex_autofix.run_deploy_worker_once(dry_run=True)
        self.assertEqual("dry_run", result["status"])
        self.assertFalse(result["processed"])
        self.assertEqual("autofix_deploy_approved", result["would_process"])

    def test_expired_deployment_approval_is_persisted_without_restart(self) -> None:
        started, repaired, _merged = self._prepare_merged_patch()
        codex_autofix.approve_autofix_deploy(
            request_id="incident-test",
            commit=str(repaired["repair_commit"]),
            now=started + timedelta(minutes=4),
        )
        restarts: list[str] = []
        result = codex_autofix.execute_deployment(
            codex_autofix._load_json(codex_autofix._state_path("incident-test")),
            repository=self.repository,
            now=started + timedelta(minutes=35),
            restart_runner=lambda: restarts.append("restart"),
        )
        self.assertEqual("auto_deploy_blocked", result["status"])
        self.assertEqual("deploy_approval_expired", result["failure_category"])
        self.assertEqual([], restarts)

    def test_active_deployment_cannot_be_cancelled_mid_restart(self) -> None:
        self._request()
        codex_autofix._save_state(
            {"request_id": "incident-test", "status": "autofix_deploying"},
            event="autofix_deploying",
        )
        with self.assertRaises(codex_autofix.AutofixError) as context:
            codex_autofix.cancel_autofix(
                request_id="incident-test",
                reason="unsafe interruption",
            )
        self.assertEqual("invalid_transition", context.exception.category)

    def test_approval_expires_fail_closed_and_cancel_is_idempotent(self) -> None:
        self._request()
        started = datetime(2026, 7, 15, tzinfo=UTC)
        approved = codex_autofix.approve_autofix(
            request_id="incident-test",
            now=started,
            repository=self.repository,
        )
        self.assertEqual("autofix_approved", approved["status"])
        self.assertEqual(
            "auto_blocked",
            codex_autofix.autofix_status(
                request_id="incident-test",
                now=started + timedelta(hours=25),
            )["status"],
        )
        cancelled = codex_autofix.cancel_autofix(
            request_id="incident-test",
            reason="Administrator review",
            now=started + timedelta(minutes=5),
        )
        repeated = codex_autofix.cancel_autofix(
            request_id="incident-test",
            reason="Repeated command",
            now=started + timedelta(minutes=6),
        )
        self.assertEqual("auto_cancelled", cancelled["status"])
        self.assertEqual(cancelled, repeated)

    def test_dry_run_reports_an_eligible_approval_without_mutation(self) -> None:
        self._request()
        codex_autofix.approve_autofix(
            request_id="incident-test",
            now=datetime.now(UTC),
            repository=self.repository,
        )
        result = codex_autofix.run_worker_once(dry_run=True)
        self.assertEqual("dry_run", result["status"])
        self.assertFalse(result["processed"])
        self.assertEqual("autofix_approved", result["would_process"])

    def test_worker_persists_an_expired_approval_as_blocked(self) -> None:
        self._request()
        started = datetime(2026, 7, 15, tzinfo=UTC)
        codex_autofix.approve_autofix(
            request_id="incident-test",
            now=started,
            repository=self.repository,
        )
        state = codex_autofix._load_json(codex_autofix._state_path("incident-test"))
        result = codex_autofix.execute_repair(
            state,
            repository=self.repository,
            now=started + timedelta(hours=25),
        )
        self.assertEqual("auto_blocked", result["status"])
        persisted = codex_autofix._load_json(codex_autofix._state_path("incident-test"))
        self.assertEqual("approval_expired", persisted["failure_category"])

    def test_repair_commit_second_approval_and_fast_forward_merge(self) -> None:
        started, repaired = self._prepare_ready_patch()
        self.assertRegex(str(repaired["repair_commit"]), r"^[0-9a-f]{40}$")
        merge_approved = codex_autofix.approve_autofix_merge(
            request_id="incident-test",
            commit=str(repaired["repair_commit"]),
            now=started + timedelta(minutes=2),
        )
        self.assertEqual("autofix_merge_approved", merge_approved["status"])
        merged = codex_autofix.execute_merge(
            codex_autofix._load_json(codex_autofix._state_path("incident-test")),
            repository=self.repository,
            now=started + timedelta(minutes=3),
            validator=lambda _path, _base: ["post-merge validator passed"],
        )
        self.assertEqual("auto_merged_pending_deploy", merged["status"])
        self.assertEqual(repaired["repair_commit"], self._git("rev-parse", "HEAD"))
        self.assertIn(
            "Autofix verified repair", (self.repository / "README.md").read_text(encoding="utf-8")
        )

    def test_dirty_target_blocks_merge_and_allows_a_fresh_second_approval(self) -> None:
        started, repaired = self._prepare_ready_patch()
        codex_autofix.approve_autofix_merge(
            request_id="incident-test",
            commit=str(repaired["repair_commit"]),
            now=started + timedelta(minutes=2),
        )
        (self.repository / "operator-note.tmp").write_text("dirty\n", encoding="utf-8")
        blocked = codex_autofix.execute_merge(
            codex_autofix._load_json(codex_autofix._state_path("incident-test")),
            repository=self.repository,
            now=started + timedelta(minutes=3),
            validator=lambda _path, _base: ["must not run"],
        )
        self.assertEqual("auto_merge_blocked", blocked["status"])
        self.assertEqual("target_dirty", blocked["failure_category"])
        (self.repository / "operator-note.tmp").unlink()
        renewed = codex_autofix.approve_autofix_merge(
            request_id="incident-test",
            commit=str(repaired["repair_commit"]),
            now=started + timedelta(minutes=4),
        )
        self.assertEqual("autofix_merge_approved", renewed["status"])

    def test_changed_target_head_blocks_merge(self) -> None:
        started, repaired = self._prepare_ready_patch()
        codex_autofix.approve_autofix_merge(
            request_id="incident-test",
            commit=str(repaired["repair_commit"]),
            now=started + timedelta(minutes=2),
        )
        (self.repository / "README.md").write_text(
            "# Analytics\nOperator committed another change.\n",
            encoding="utf-8",
        )
        self._git("add", "--", "README.md")
        self._git(
            "-c",
            "user.name=Autofix Test",
            "-c",
            "user.email=autofix@example.com",
            "commit",
            "-m",
            "operator change",
        )
        result = codex_autofix.execute_merge(
            codex_autofix._load_json(codex_autofix._state_path("incident-test")),
            repository=self.repository,
            now=started + timedelta(minutes=3),
            validator=lambda _path, _base: ["must not run"],
        )
        self.assertEqual("auto_merge_blocked", result["status"])
        self.assertEqual("target_head_changed", result["failure_category"])

    def test_worker_lock_rejects_parallel_execution(self) -> None:
        with codex_autofix._worker_lock():
            with self.assertRaises(codex_autofix.AutofixError) as context:
                with codex_autofix._worker_lock():
                    self.fail("parallel lock unexpectedly succeeded")
        self.assertEqual("worker_busy", context.exception.category)

    def test_post_merge_validation_failure_is_reported_as_already_merged(self) -> None:
        started, repaired = self._prepare_ready_patch()
        codex_autofix.approve_autofix_merge(
            request_id="incident-test",
            commit=str(repaired["repair_commit"]),
            now=started + timedelta(minutes=2),
        )

        def failed_validator(_path: Path, _base: str) -> list[str]:
            raise codex_autofix.AutofixError("post_merge_test_failed", "synthetic failure")

        result = codex_autofix.execute_merge(
            codex_autofix._load_json(codex_autofix._state_path("incident-test")),
            repository=self.repository,
            now=started + timedelta(minutes=3),
            validator=failed_validator,
        )
        self.assertEqual("auto_merged_validation_failed", result["status"])
        self.assertEqual(repaired["repair_commit"], self._git("rev-parse", "HEAD"))

    def test_merge_commit_hash_mismatch_is_rejected(self) -> None:
        self._request()
        state = {
            "request_id": "incident-test",
            "status": "auto_patch_ready",
            "repair_commit": "a" * 40,
            "base_commit": "b" * 40,
        }
        codex_autofix._save_state(state, event="auto_patch_ready")
        with self.assertRaises(codex_autofix.AutofixError) as context:
            codex_autofix.approve_autofix_merge(
                request_id="incident-test",
                commit="c" * 40,
            )
        self.assertEqual("commit_mismatch", context.exception.category)


if __name__ == "__main__":
    unittest.main()
