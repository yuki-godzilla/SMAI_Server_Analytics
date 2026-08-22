import json
import tempfile
import unittest
from pathlib import Path

from smai_analytics import network


class ServerAnalyticsNetworkTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_path = Path(self.temp_dir.name) / "network.json"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def write_config(self, value: dict[str, object]) -> None:
        self.config_path.write_text(json.dumps(value), encoding="utf-8")

    def test_magicdns_urls_share_one_hostname_and_keep_ports_distinct(self) -> None:
        settings = network.load_network_settings()
        urls = network.resolve_network_urls(settings)

        self.assertEqual("smai-server", settings.tailscale_hostname)
        self.assertEqual(8501, settings.main_application.port)
        self.assertEqual(8502, settings.server_analytics.port)
        self.assertEqual("http://smai-server:8501", urls.main_application_url)
        self.assertEqual("http://smai-server:8502", urls.server_analytics_url)
        self.assertEqual("http://localhost:8502", urls.analytics_local_url)

    def test_environment_overrides_preserve_the_shared_hostname_contract(self) -> None:
        settings = network.load_network_settings(
            environ={
                "SMAI_TAILSCALE_HOSTNAME": "smai-server",
                "SMAI_MAIN_PORT": "18501",
                "SMAI_ANALYTICS_PORT": "18502",
            }
        )
        urls = network.resolve_network_urls(settings)

        self.assertEqual("smai-server", urls.hostname)
        self.assertEqual("http://smai-server:18501", urls.main_application_url)
        self.assertEqual("http://smai-server:18502", urls.server_analytics_url)

    def test_port_collision_is_rejected(self) -> None:
        self.write_config(
            {
                "network": {
                    "tailscale_hostname": "smai-server",
                    "main_application": {"scheme": "http", "port": 8502},
                    "server_analytics": {"scheme": "http", "port": 8502},
                }
            }
        )

        with self.assertRaisesRegex(network.NetworkConfigurationError, "重複"):
            network.load_network_settings(config_path=self.config_path)

    def test_user_facing_url_rejects_bind_addresses_and_ip_addresses(self) -> None:
        for hostname in ("0.0.0.0", "localhost", "192.168.68.50", "100.111.89.60"):
            with self.subTest(hostname=hostname):
                with self.assertRaises(network.NetworkConfigurationError):
                    network.build_server_analytics_url(hostname, 8502)

    def test_flat_legacy_settings_migrate_without_lan_or_remote_url_branches(self) -> None:
        self.write_config(
            {
                "tailscale_hostname": "smai-server",
                "main_application_port": 8501,
                "analytics_port": 8502,
            }
        )

        urls = network.resolve_network_urls(network.load_network_settings(config_path=self.config_path))

        self.assertEqual("http://smai-server:8502", urls.server_analytics_url)
        self.assertNotIn("192.168.", urls.server_analytics_url)
        self.assertNotIn("100.", urls.server_analytics_url)

    def test_url_resolution_never_depends_on_the_tailscale_cli(self) -> None:
        self.assertEqual("http://smai-server:8502", network.resolve_network_urls().server_analytics_url)


if __name__ == "__main__":
    unittest.main()
