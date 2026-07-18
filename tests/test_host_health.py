import json
import subprocess
import unittest

from smai_analytics.monitoring import health, host_health


class HostHealthTests(unittest.TestCase):
    def test_host_checks_mark_recent_unexpected_shutdown_for_attention(self) -> None:
        payload = {
            "tailscale_status": "Up",
            "disks": [{"health": "Healthy", "operational": "OK"}],
            "memory_free_percent": 42.0,
            "cpu_percent": 15.0,
            "unexpected_shutdown_events": 2,
        }

        def runner(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess([], 0, json.dumps(payload), "")

        checks = host_health.collect_checks(runner=runner)
        by_name = {str(item["name"]): item for item in checks}
        self.assertEqual("ok", by_name["Tailscale adapter"]["status"])
        self.assertEqual("ok", by_name["Physical disk health"]["status"])
        self.assertEqual("degraded", by_name["Unexpected shutdown events"]["status"])

    def test_host_query_failure_is_unknown_not_healthy(self) -> None:
        def runner(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess([], 1, "", "failure")

        checks = host_health.collect_checks(runner=runner)
        self.assertEqual("unknown", checks[0]["status"])

    def test_gpu_telemetry_is_optional_and_only_flags_high_temperature(self) -> None:
        payload = {
            "tailscale_status": "Up",
            "disks": [{"health": "Healthy", "operational": "OK"}],
            "memory_free_percent": 42.0,
            "cpu_percent": 15.0,
            "unexpected_shutdown_events": 0,
            "gpus": [{"temperature_c": 86.0, "fan_percent": 70.0, "power_draw_w": 120.0}],
        }

        def runner(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess([], 0, json.dumps(payload), "")

        checks = {str(item["name"]): item for item in host_health.collect_checks(runner=runner)}
        self.assertEqual("degraded", checks["GPU thermal"]["status"])
        self.assertIn("86", str(checks["GPU thermal"]["detail"]))

    def test_absent_gpu_does_not_change_host_health(self) -> None:
        payload = {
            "tailscale_status": "Up",
            "disks": [{"health": "Healthy", "operational": "OK"}],
            "memory_free_percent": 42.0,
            "cpu_percent": 15.0,
            "unexpected_shutdown_events": 0,
            "gpus": [],
        }

        def runner(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess([], 0, json.dumps(payload), "")

        self.assertNotIn("GPU thermal", {str(item["name"]) for item in host_health.collect_checks(runner=runner)})

    def test_health_snapshot_degrades_on_noncritical_host_attention(self) -> None:
        snapshot = health.collect(
            host_checks=[
                {
                    "name": "Unexpected shutdown events",
                    "level": "L3",
                    "status": "degraded",
                    "detail": "unexpected shutdown events in 24h: 1",
                    "latency_ms": None,
                }
            ]
        )
        self.assertEqual("degraded", snapshot["overall"])

    def test_health_snapshot_escalates_a_critical_data_check(self) -> None:
        snapshot = health.collect(
            host_checks=[],
            freshness_checks=[
                {
                    "name": "Market news freshness",
                    "level": "L2",
                    "status": "critical",
                    "detail": "更新停止の可能性",
                }
            ],
        )
        self.assertEqual("critical", snapshot["overall"])


if __name__ == "__main__":
    unittest.main()
