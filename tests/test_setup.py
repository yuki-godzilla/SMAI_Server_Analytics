import subprocess
import unittest
from pathlib import Path

import tomllib

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SETUP_ROOT = REPOSITORY_ROOT / "setup"


class SetupLayoutTests(unittest.TestCase):
    def test_setup_keeps_runtime_and_development_dependencies_separate(self) -> None:
        runtime = (SETUP_ROOT / "requirements.txt").read_text(encoding="utf-8")
        development = (SETUP_ROOT / "requirements-dev.txt").read_text(encoding="utf-8")

        self.assertIn("Pillow==10.4.0", runtime)
        self.assertIn("streamlit==1.38.0", runtime)
        self.assertIn("pytest==8.3.2", development)
        self.assertIn("ruff==0.6.3", development)

    def test_setup_uses_a_dedicated_analytics_virtual_environment(self) -> None:
        setup_script = (SETUP_ROOT / "setup.bat").read_text(encoding="utf-8")

        self.assertIn("set \"VENV_NAME=venv_SMAI_Analytics\"", setup_script)
        self.assertIn("The existing virtual environment is reused", setup_script)
        self.assertNotIn("rmdir /s /q", setup_script.casefold())

    def test_streamlit_configuration_is_local_by_default(self) -> None:
        config = (REPOSITORY_ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")

        self.assertIn('address = "127.0.0.1"', config)
        self.assertIn("port = 8502", config)
        self.assertIn("enableWebsocketCompression = true", config)

    def test_project_tooling_configuration_matches_the_setup_layout(self) -> None:
        with (REPOSITORY_ROOT / "pyproject.toml").open("rb") as stream:
            configuration = tomllib.load(stream)

        self.assertEqual(configuration["tool"]["pytest"]["ini_options"]["testpaths"], ["tests"])
        self.assertEqual(configuration["tool"]["ruff"]["line-length"], 100)

    def test_launchers_prefer_the_analytics_virtual_environment(self) -> None:
        web = (REPOSITORY_ROOT / "run_analytics_web.bat").read_text(encoding="utf-8")

        self.assertIn("venv_SMAI_Analytics\\Scripts\\python.exe", web)
        self.assertIn("SMAI_COMPATIBILITY_PYTHON", web)

    def test_implementation_is_grouped_by_responsibility_with_compatibility_entrypoints(self) -> None:
        expected_modules = (
            REPOSITORY_ROOT / "smai_analytics" / "monitoring" / "health.py",
            REPOSITORY_ROOT / "smai_analytics" / "monitoring" / "telemetry.py",
            REPOSITORY_ROOT / "smai_analytics" / "operations" / "backup.py",
            REPOSITORY_ROOT / "smai_analytics" / "operations" / "retention.py",
            REPOSITORY_ROOT / "smai_analytics" / "ui" / "web_dashboard.py",
            REPOSITORY_ROOT / "config" / "retention_policy.json",
        )

        self.assertTrue(all(path.is_file() for path in expected_modules))
        self.assertIn("compatibility entry point", (REPOSITORY_ROOT / "analytics_web.py").read_text(encoding="utf-8").casefold())
        self.assertIn("compatibility entry point", (REPOSITORY_ROOT / "health.py").read_text(encoding="utf-8").casefold())

    def test_setup_help_is_available_without_creating_a_virtual_environment(self) -> None:
        result = subprocess.run(
            ["cmd.exe", "/d", "/c", r"setup\setup.bat --help"],
            cwd=REPOSITORY_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Usage: setup\\setup.bat", result.stdout)


if __name__ == "__main__":
    unittest.main()
