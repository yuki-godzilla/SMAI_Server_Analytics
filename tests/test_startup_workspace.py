import unittest
from pathlib import Path

from smai_analytics.ui import web_dashboard


class StartupWorkspaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parents[1]
        self.scripts = self.root / "scripts"

    def read(self, name: str) -> str:
        return (self.scripts / name).read_text(encoding="utf-8")

    def test_analytics_startup_is_duplicate_safe_and_user_owned(self) -> None:
        service = self.read("start_smai_analytics_service.ps1")
        registration = self.read("register_smai_analytics_autostart_task.ps1")

        self.assertIn("Test-AnalyticsHealth", service)
        self.assertIn("Get-NetTCPConnection", service)
        self.assertIn("StartupDelaySeconds", service)
        self.assertIn("[Environment+SpecialFolder]::Startup", registration)
        self.assertIn("SMAI Analytics Autostart.cmd", registration)
        self.assertIn("-StartupDelaySeconds 45", registration)

    def test_workspace_opens_main_prompt_and_pages_without_starting_servers(self) -> None:
        prompt = self.read("show_smai_service_prompt.ps1")
        pages = self.read("open_smai_service_pages.ps1")
        workspace = self.read("start_smai_operations_workspace.ps1")
        registration = self.read("register_smai_operations_workspace_task.ps1")

        self.assertIn("Local\\SMAI-$Service-Operations-Prompt", prompt)
        self.assertIn("does not start a duplicate instance", prompt)
        self.assertIn("http://127.0.0.1:8501/_stcore/health", pages)
        self.assertIn("http://127.0.0.1:8502/_stcore/health", pages)
        self.assertIn("Start-Process $target.page", pages)
        self.assertIn('foreach ($service in @(\"Main\"))', workspace)
        self.assertNotIn('foreach ($service in @(\"Main\", \"Analytics\"))', workspace)
        self.assertIn("SMAI Operations Workspace.cmd", registration)

    def test_dashboard_does_not_require_a_nonexistent_workspace_scheduler_task(self) -> None:
        self.assertNotIn("SMAI-Operations-Workspace", web_dashboard.TASKS)
        self.assertNotIn("SMAI-Analytics-Startup-User", web_dashboard.TASKS)


if __name__ == "__main__":
    unittest.main()
