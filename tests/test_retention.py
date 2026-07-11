import tempfile
import time
import unittest
from pathlib import Path

import retention


class RetentionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="smai-retention-", dir=str(Path.cwd()))
        self.runtime = Path(self.temp_dir.name) / "runtime"
        (self.runtime / "logs").mkdir(parents=True)
        (self.runtime / "backups").mkdir()
        self.now = time.time()
        self.policy = {"log_days": 30, "backup_days": 30}

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _age(self, path: Path, days: int) -> None:
        timestamp = self.now - days * 86400
        path.touch()
        path.stat()
        import os

        os.utime(path, (timestamp, timestamp))

    def test_candidates_include_old_logs_and_complete_tool_backups_only(self) -> None:
        old_log = self.runtime / "logs" / "old.log"
        new_log = self.runtime / "logs" / "new.log"
        old_backup = self.runtime / "backups" / "smai_20260101_000000"
        incomplete_backup = self.runtime / "backups" / "smai_incomplete"
        foreign_backup = self.runtime / "backups" / "manual-copy"
        for directory in (old_backup, incomplete_backup, foreign_backup):
            directory.mkdir()
        (old_backup / "manifest.json").write_text("{}", encoding="utf-8")
        self._age(old_log, 31)
        new_log.write_text("new", encoding="utf-8")
        self._age(old_backup, 31)
        self._age(incomplete_backup, 31)
        self._age(foreign_backup, 31)

        candidates = retention.retention_candidates(self.runtime, self.policy, now=self.now)

        self.assertEqual(candidates["logs"], [old_log])
        self.assertEqual(candidates["backups"], [old_backup])

    def test_dry_run_does_not_delete_and_apply_removes_only_candidates(self) -> None:
        old_log = self.runtime / "logs" / "old.log"
        old_backup = self.runtime / "backups" / "smai_20260101_000000"
        old_backup.mkdir()
        (old_backup / "manifest.json").write_text("{}", encoding="utf-8")
        self._age(old_log, 31)
        self._age(old_backup, 31)
        candidates = retention.retention_candidates(self.runtime, self.policy, now=self.now)

        self.assertEqual(retention.apply_retention(candidates, dry_run=True), {"logs": 0, "backups": 0})
        self.assertTrue(old_log.exists())
        self.assertTrue(old_backup.exists())
        self.assertEqual(retention.apply_retention(candidates), {"logs": 1, "backups": 1})
        self.assertFalse(old_log.exists())
        self.assertFalse(old_backup.exists())


if __name__ == "__main__":
    unittest.main()
