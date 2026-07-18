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
        self.assertIn("run_analytics_web.ps1", service)
        self.assertIn("Local\\SMAI-Analytics-Service-Start", service)
        self.assertIn("WindowStyle = \"Hidden\"", service)
        self.assertIn("[Environment+SpecialFolder]::Startup", registration)
        self.assertIn("SMAI Analytics Autostart.lnk", registration)
        self.assertIn("WScript.Shell", registration)
        self.assertIn("SMAI-Server-Analytics", registration)
        self.assertIn("Disabled legacy CMD task", registration)
        self.assertIn("-StartupDelaySeconds 45", registration)

    def test_workspace_opens_colored_prompts_and_pages_without_starting_servers(self) -> None:
        prompt = self.read("show_smai_service_prompt.ps1")
        pages = self.read("open_smai_service_pages.ps1")
        workspace = self.read("start_smai_operations_workspace.ps1")
        registration = self.read("register_smai_operations_workspace_task.ps1")

        self.assertIn("Local\\SMAI-$Service-Operations-Prompt", prompt)
        self.assertIn("does not start a duplicate instance", prompt)
        self.assertIn('-ForegroundColor $status.color', prompt)
        self.assertIn('color = "Green"', prompt)
        self.assertIn('color = "Yellow"', prompt)
        self.assertIn('color = "Red"', prompt)
        self.assertIn("http://127.0.0.1:8501/_stcore/health", pages)
        self.assertIn("http://127.0.0.1:8502/_stcore/health", pages)
        self.assertIn("Start-Process $target.page", pages)
        self.assertIn('foreach ($service in @(\"Main\", \"Analytics\"))', workspace)
        self.assertIn("SMAI Operations Workspace.lnk", registration)
        self.assertIn("WScript.Shell", registration)

    def test_powershell_web_launcher_keeps_the_server_runner_out_of_cmd(self) -> None:
        launcher = self.read("run_analytics_web.ps1")

        self.assertIn("venv_SMAI_Analytics\\Scripts\\python.exe", launcher)
        self.assertIn("compatibilityPython", launcher)
        self.assertIn("-m smai_analytics.network --emit-batch", launcher)
        self.assertIn("--server.address 0.0.0.0", launcher)
        self.assertIn("--server.enableXsrfProtection true", launcher)
        self.assertNotIn("cmd.exe", launcher.casefold())

    def test_host_monitor_uses_a_non_console_launcher(self) -> None:
        registration = self.read("register_smai_host_monitor_task.ps1")
        runner = self.read("run_smai_host_monitor.ps1")

        self.assertIn("run_smai_host_monitor.ps1", registration)
        self.assertIn("run_hidden_powershell.vbs", registration)
        self.assertIn("wscript.exe", registration)
        self.assertIn("health.py", runner)
        self.assertIn("observe_tasks.py", runner)
        self.assertNotIn("cmd.exe", runner.casefold())

    def test_periodic_tasks_use_hidden_powershell_launchers(self) -> None:
        incident = self.read("register_incident_automation_task.ps1")
        backup = self.read("register_backup_restore_smoke_task.ps1")
        maintenance = self.read("register_smai_host_maintenance_task.ps1")
        runner = self.read("run_incident_automation_task.ps1")

        self.assertIn("run_incident_automation_task.ps1", incident)
        self.assertIn("run_hidden_powershell.vbs", incident)
        self.assertIn("run_backup_restore_smoke_hidden.vbs", backup)
        self.assertNotIn("run_backup_restore_smoke.cmd", backup)
        self.assertIn("-WindowStyle Hidden", maintenance)
        self.assertIn('ValidateSet("once", "autofix-worker", "autofix-deploy-worker")', runner)
        self.assertNotIn("cmd.exe", runner.casefold())

    def test_hidden_launcher_uses_a_gui_host_and_waits_for_completion(self) -> None:
        launcher = self.read("run_hidden_powershell.vbs")

        self.assertIn('CreateObject("WScript.Shell")', launcher)
        self.assertIn('command = QuoteArgument(CStr(WScript.Arguments(0)))', launcher)
        self.assertIn('For index = 1 To WScript.Arguments.Count - 1', launcher)
        self.assertNotIn('command = ""', launcher)
        self.assertIn("shell.Run(command, 0, True)", launcher)
        self.assertIn("WScript.Quit exitCode", launcher)

    def test_runtime_retention_runs_daily_without_a_console(self) -> None:
        registration = self.read("register_smai_runtime_retention_task.ps1")
        runner = self.read("run_smai_retention.ps1")

        self.assertIn('New-ScheduledTaskTrigger -Daily -At "03:45"', registration)
        self.assertIn("SMAI-Runtime-Retention", registration)
        self.assertIn("run_hidden_powershell.vbs", registration)
        self.assertIn("retention.py", runner)

    def test_dashboard_does_not_require_a_nonexistent_workspace_scheduler_task(self) -> None:
        self.assertNotIn("SMAI-Operations-Workspace", web_dashboard.TASKS)
        self.assertNotIn("SMAI-Analytics-Startup-User", web_dashboard.TASKS)
        self.assertNotIn("SMAI-Server-Analytics", web_dashboard.TASKS)


if __name__ == "__main__":
    unittest.main()
