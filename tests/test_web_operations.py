import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class WebOperationsContractTests(unittest.TestCase):
    def test_web_launcher_is_the_magicdns_operations_entrypoint(self) -> None:
        launcher = (REPOSITORY_ROOT / "run_analytics_web.bat").read_text(encoding="utf-8")
        network_config = (REPOSITORY_ROOT / "config" / "network.json").read_text(encoding="utf-8")

        self.assertIn("analytics_web.py", launcher)
        self.assertIn("--server.address 0.0.0.0", launcher)
        self.assertIn("-m smai_analytics.network --emit-batch", launcher)
        self.assertNotIn("SMAI_ANALYTICS_LAN_IP", launcher)
        self.assertIn('"tailscale_hostname": "smai-server"', network_config)
        self.assertIn('"port": 8502', network_config)
        self.assertIn("--server.enableXsrfProtection true", launcher)
        self.assertNotIn("dashboard.py", launcher.casefold())

    def test_autostart_keeps_one_web_console_per_interactive_user(self) -> None:
        script = (
            REPOSITORY_ROOT / "scripts" / "register_smai_analytics_autostart_task.ps1"
        ).read_text(encoding="utf-8")

        self.assertIn("run_analytics_web.bat", script)
        self.assertIn("SMAI-Server-Analytics", script)
        self.assertIn("-MultipleInstances IgnoreNew", script)
        self.assertIn("-LogonType Interactive", script)
        self.assertIn("-RestartCount 3", script)
        self.assertNotIn("run_dashboard.bat", script)

    def test_restart_targets_only_the_web_console_process(self) -> None:
        script = (REPOSITORY_ROOT / "scripts" / "restart_analytics_web.ps1").read_text(
            encoding="utf-8"
        )
        launcher = (REPOSITORY_ROOT / "restart_analytics_web.bat").read_text(encoding="utf-8")

        self.assertIn("analytics_web.py", script)
        self.assertIn("run_analytics_web.bat", script)
        self.assertIn("-WindowStyle Hidden", script)
        self.assertIn("Get-Process -Id $process.Id -ErrorAction SilentlyContinue", script)
        self.assertIn("restart_analytics_web.ps1", launcher)
        self.assertNotIn("dashboard.py", script.casefold())

    def test_tkinter_implementation_and_legacy_launchers_are_absent(self) -> None:
        legacy_paths = (
            REPOSITORY_ROOT / "dashboard.py",
            REPOSITORY_ROOT / "run_dashboard.bat",
            REPOSITORY_ROOT / "restart_dashboard.bat",
            REPOSITORY_ROOT / "scripts" / "restart_dashboard.ps1",
            REPOSITORY_ROOT / "smai_analytics" / "ui" / "dashboard.py",
            REPOSITORY_ROOT / "tests" / "test_dashboard.py",
            REPOSITORY_ROOT / "tests" / "ui_dashboard_visual_sprint.py",
        )

        self.assertTrue(all(not path.exists() for path in legacy_paths))


if __name__ == "__main__":
    unittest.main()
