import unittest

from smai_analytics.monitoring import task_observer


class TaskObserverTests(unittest.TestCase):
    def test_active_autofix_adds_the_candidate_worker_without_deployment(self) -> None:
        names = task_observer.task_names()

        self.assertIn("SMAI-Runtime-Retention", names)
        self.assertIn("SMAI-Host-Monitor", names)
        self.assertIn("SMAI-Codex-Autofix-Worker", names)
        self.assertNotIn("SMAI-Codex-Autofix-Deploy", names)

    def test_expected_roots_preserve_the_analytics_main_boundary(self) -> None:
        self.assertEqual(task_observer.REPOSITORY_ROOT, task_observer.expected_task_root("SMAI-Runtime-Retention"))
        self.assertEqual(task_observer.PROJECT_ROOT, task_observer.expected_task_root("SmartMarketAI-Server-Watch"))


if __name__ == "__main__":
    unittest.main()
