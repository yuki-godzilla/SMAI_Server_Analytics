from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from smai_analytics.operations import admin_settings


class AdministratorSettingsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="smai-admin-settings-")
        self.settings_path = admin_settings.SETTINGS_PATH
        admin_settings.SETTINGS_PATH = Path(self.temp_dir.name) / "administrator_settings.json"

    def tearDown(self) -> None:
        admin_settings.SETTINGS_PATH = self.settings_path
        self.temp_dir.cleanup()

    def test_profile_is_saved_only_to_the_runtime_settings_path(self) -> None:
        saved = admin_settings.save_profile(
            administrator_name="Operations Admin",
            administrator_email="admin@example.com",
        )

        self.assertEqual("Operations Admin", saved["administrator_name"])
        self.assertEqual("admin@example.com", saved["administrator_email"])
        persisted = json.loads(admin_settings.SETTINGS_PATH.read_text(encoding="utf-8"))
        self.assertEqual("admin@example.com", persisted["administrator_email"])

    def test_notification_preferences_filter_only_the_matching_delivery_kinds(self) -> None:
        admin_settings.save_operations(
            incident_detection=False,
            repair_report=True,
            recovery_result=False,
            auto_repair_candidate=True,
        )

        self.assertFalse(admin_settings.notification_allowed("incident"))
        self.assertFalse(admin_settings.notification_allowed("repeat"))
        self.assertTrue(admin_settings.notification_allowed("autofix_ready"))
        self.assertFalse(admin_settings.notification_allowed("recovery"))
        self.assertTrue(admin_settings.auto_repair_candidate_requested())

    def test_invalid_profile_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            admin_settings.save_profile(administrator_name="", administrator_email="not-an-email")


if __name__ == "__main__":
    unittest.main()
