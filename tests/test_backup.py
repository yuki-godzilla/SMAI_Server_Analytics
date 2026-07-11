import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import backup


class BackupCreateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="smai-backup-", dir=str(Path.cwd()))
        self.project_root = Path(self.temp_dir.name) / "project"
        self.runtime_root = Path(self.temp_dir.name) / "runtime"
        self.project_root.mkdir(parents=True, exist_ok=True)
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        (self.project_root / "data" / "user").mkdir(parents=True, exist_ok=True)
        (self.project_root / "data" / "ops").mkdir(parents=True, exist_ok=True)
        (self.project_root / "data" / "user" / "sample.txt").write_text("hello", encoding="utf-8")
        (self.project_root / "data" / "ops" / "state.json").write_text("{}", encoding="utf-8")
        self.original_project_root = backup.PROJECT_ROOT
        self.original_runtime_root = backup.RUNTIME_ROOT
        self.original_sources = backup.SOURCES
        backup.PROJECT_ROOT = self.project_root
        backup.RUNTIME_ROOT = self.runtime_root
        backup.SOURCES = (
            self.project_root / "data" / "user",
            self.project_root / "data" / "ops",
            self.project_root / "data" / "marketdata" / "symbol_universe.csv",
        )

    def tearDown(self) -> None:
        backup.PROJECT_ROOT = self.original_project_root
        backup.RUNTIME_ROOT = self.original_runtime_root
        backup.SOURCES = self.original_sources
        self.temp_dir.cleanup()

    def test_create_skips_inaccessible_files(self) -> None:
        original_copy2 = shutil.copy2

        def copy_with_failure(src: str | Path, dst: str | Path, *args, **kwargs):
            if Path(src).name == "sample.txt":
                raise PermissionError("locked")
            return original_copy2(src, dst, *args, **kwargs)

        with patch("backup.shutil.copy2", side_effect=copy_with_failure):
            destination = backup.create()

        manifest = json.loads((destination / "manifest.json").read_text(encoding="utf-8"))
        statuses = {entry["path"]: entry.get("status", "ok") for entry in manifest["files"]}
        self.assertEqual(statuses["data/user/sample.txt"], "skipped")
        self.assertEqual(statuses["data/ops/state.json"], "ok")

    def test_restore_restores_files_from_backup(self) -> None:
        destination = backup.create()
        target_path = self.project_root / "data" / "user" / "sample.txt"
        target_path.unlink()
        self.assertFalse(target_path.exists())

        restored = backup.restore(destination)

        self.assertTrue(restored)
        self.assertTrue(target_path.exists())
        self.assertEqual(target_path.read_text(encoding="utf-8"), "hello")

    def test_restore_rejects_tampered_backup_before_writing(self) -> None:
        destination = backup.create()
        target_path = self.project_root / "data" / "user" / "sample.txt"
        target_path.write_text("keep this value", encoding="utf-8")
        (destination / "data" / "user" / "sample.txt").write_text("tampered", encoding="utf-8")

        self.assertFalse(backup.verify(destination))
        self.assertFalse(backup.restore(destination))
        self.assertEqual(target_path.read_text(encoding="utf-8"), "keep this value")

    def test_restore_can_target_an_isolated_directory(self) -> None:
        destination = backup.create()
        isolated = Path(self.temp_dir.name) / "restore-check"

        self.assertTrue(backup.restore(destination, isolated))
        self.assertEqual(
            (isolated / "data" / "user" / "sample.txt").read_text(encoding="utf-8"),
            "hello",
        )

    def test_verify_rejects_manifest_path_escape(self) -> None:
        destination = backup.create()
        manifest_path = destination / "manifest.json"
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        payload["files"][0]["path"] = "../outside.txt"
        manifest_path.write_text(json.dumps(payload), encoding="utf-8")

        self.assertFalse(backup.verify(destination))
        self.assertFalse(backup.restore(destination))


if __name__ == "__main__":
    unittest.main()
