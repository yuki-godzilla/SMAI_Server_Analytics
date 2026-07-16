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

    def test_autostart_uses_the_current_users_startup_folder_and_avoids_duplicates(self) -> None:
        script = (
            REPOSITORY_ROOT / "scripts" / "register_smai_analytics_autostart_task.ps1"
        ).read_text(encoding="utf-8")

        self.assertIn("start_smai_analytics_service.ps1", script)
        self.assertIn("[Environment+SpecialFolder]::Startup", script)
        self.assertIn("SMAI Analytics Autostart.lnk", script)
        self.assertIn("WScript.Shell", script)
        self.assertIn("Disabled legacy CMD task", script)
        self.assertIn("-StartupDelaySeconds 45", script)
        self.assertNotIn("run_dashboard.bat", script)

    def test_restart_targets_only_the_web_console_process(self) -> None:
        script = (REPOSITORY_ROOT / "scripts" / "restart_analytics_web.ps1").read_text(
            encoding="utf-8"
        )
        launcher = (REPOSITORY_ROOT / "restart_analytics_web.bat").read_text(encoding="utf-8")

        self.assertIn("analytics_web.py", script)
        self.assertIn("run_analytics_web.ps1", script)
        self.assertIn('"-WindowStyle", "Hidden"', script)
        self.assertIn('WindowStyle = "Hidden"', script)
        self.assertIn("WindowsPowerShell", script)
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

    def test_codex_autofix_worker_requires_a_dedicated_user_and_keeps_deployment_disabled(self) -> None:
        register = (
            REPOSITORY_ROOT / "scripts" / "register_smai_codex_autofix_worker_task.ps1"
        ).read_text(encoding="utf-8")
        config = (REPOSITORY_ROOT / "config" / "codex_autofix.json").read_text(encoding="utf-8")

        self.assertIn("[Parameter(Mandatory)]", register)
        self.assertIn("[string]$UserId", register)
        self.assertIn("-LogonType Password", register)
        self.assertIn("-RunLevel Limited", register)
        self.assertIn("-MultipleInstances IgnoreNew", register)
        self.assertIn("-Minutes 45", register)
        self.assertIn('New-ScheduledTaskTrigger -Daily -At "00:00"', register)
        self.assertIn('PSVersionTable.PSEdition -ne "Desktop"', register)
        self.assertIn("WindowsPowerShell\\v1.0\\powershell.exe", register)
        self.assertIn("Import-Module Microsoft.PowerShell.Security -ErrorAction Stop", register)
        self.assertIn('"enabled": true', config)
        self.assertIn('"mode": "active"', config)
        self.assertIn('"deployment_enabled": false', config)

    def test_autofix_account_provisioner_requires_an_elevated_secure_local_setup(self) -> None:
        provisioner = (
            REPOSITORY_ROOT / "scripts" / "provision_smai_codex_autofix_user.ps1"
        ).read_text(encoding="utf-8")

        self.assertIn("SMAI-Codex-Autofix", provisioner)
        self.assertIn("WindowsBuiltInRole]::Administrator", provisioner)
        self.assertIn("Read-Host", provisioner)
        self.assertIn("-AsSecureString", provisioner)
        self.assertIn("New-LocalUser", provisioner)
        self.assertIn("Add-LocalGroupMember", provisioner)
        self.assertIn("CodexSandboxUsers", provisioner)
        self.assertIn("/passwordreq:yes", provisioner)
        self.assertIn("Administrators", provisioner)
        self.assertIn("icacls", provisioner)
        self.assertIn("incident_operations", provisioner)
        self.assertIn("development_environment", provisioner)

    def test_autofix_workspace_launcher_keeps_developer_state_outside_the_repository(self) -> None:
        launcher = (
            REPOSITORY_ROOT / "scripts" / "launch_smai_codex_autofix_workspace.ps1"
        ).read_text(encoding="utf-8")

        self.assertIn("SMAI_Server_Runtime\\development_environment", launcher)
        self.assertIn("vscode-shared-settings.json", launcher)
        self.assertIn("SMAI-Shared-VSCode", launcher)
        self.assertIn("--user-data-dir", launcher)
        self.assertIn("--extensions-dir", launcher)
        self.assertIn("ms-python.python", launcher)
        self.assertIn("ms-vscode.powershell", launcher)
        self.assertIn("ms-toolsai.jupyter", launcher)
        self.assertIn("openai.chatgpt", launcher)
        self.assertIn("login --device-auth", launcher)

    def test_autofix_handover_desktop_placement_requires_admin_and_uses_the_runtime_copy(self) -> None:
        placement = (
            REPOSITORY_ROOT / "scripts" / "place_smai_codex_autofix_handover_on_desktop.ps1"
        ).read_text(encoding="utf-8")

        self.assertIn("WindowsBuiltInRole]::Administrator", placement)
        self.assertIn("development_environment\\handover", placement)
        self.assertIn("SMAI-Codex-Autofix-Handover.docx", placement)
        self.assertIn("Copy-Item", placement)
        self.assertIn("WScript.Shell", placement)
        self.assertIn("SMAI-Shared-Developer-Workspace.lnk", placement)
        self.assertIn("SMAI-Codex-CLI.lnk", placement)
        self.assertIn("ChatGPT-Web.url", placement)

    def test_codex_autofix_deploy_executor_uses_the_interactive_analytics_owner(self) -> None:
        register = (
            REPOSITORY_ROOT / "scripts" / "register_smai_codex_autofix_deploy_task.ps1"
        ).read_text(encoding="utf-8")

        self.assertIn("autofix-deploy-worker", register)
        self.assertIn("-LogonType Interactive", register)
        self.assertIn("-RunLevel Limited", register)
        self.assertIn("-MultipleInstances IgnoreNew", register)
        self.assertIn('Interval = "PT1M"', register)
        self.assertIn("-Minutes 15", register)
        self.assertIn('New-ScheduledTaskTrigger -Daily -At "00:00"', register)
        self.assertNotIn("-LogonType Password", register)

    def test_incident_automation_repeats_across_calendar_days(self) -> None:
        register = (
            REPOSITORY_ROOT / "scripts" / "register_incident_automation_task.ps1"
        ).read_text(encoding="utf-8")

        self.assertIn('New-ScheduledTaskTrigger -Daily -At "00:00"', register)
        self.assertIn('Interval = "PT5M"', register)
        self.assertIn('Duration = "P1D"', register)
        self.assertIn("venv_SMAI_Analytics", register)
        self.assertNotIn("Get-Command python.exe", register)

    def test_backup_restore_smoke_is_monthly_and_uses_an_isolated_runner(self) -> None:
        register = (
            REPOSITORY_ROOT / "scripts" / "register_backup_restore_smoke_task.ps1"
        ).read_text(encoding="utf-8")
        runner = (
            REPOSITORY_ROOT / "scripts" / "run_backup_restore_smoke.ps1"
        ).read_text(encoding="utf-8")
        hidden_launcher = (
            REPOSITORY_ROOT / "scripts" / "run_backup_restore_smoke_hidden.vbs"
        ).read_text(encoding="utf-8")

        self.assertIn('"SMAI-Backup-Restore-Smoke"', register)
        self.assertIn('"MONTHLY"', register)
        self.assertIn('"02:00"', register)
        self.assertIn('"/IT"', register)
        self.assertIn('"/RL", "LIMITED"', register)
        self.assertIn("run_backup_restore_smoke_hidden.vbs", register)
        self.assertIn("wscript.exe", register)
        self.assertNotIn("run_backup_restore_smoke.cmd", register)
        self.assertIn("backup.py", runner)
        self.assertIn(" smoke", runner)
        self.assertIn("venv_SMAI_Analytics", runner)
        self.assertIn("run_backup_restore_smoke.ps1", hidden_launcher)
        self.assertIn("shell.Run(command, 0, True)", hidden_launcher)


if __name__ == "__main__":
    unittest.main()
