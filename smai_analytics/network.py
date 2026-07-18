"""Resolve safe, user-facing URLs for the SMAI Server Analytics console.

The Console and the SMAI Main Application share one Tailscale device name, but
they deliberately keep their ports and URL settings separate. This module
never needs the Tailscale CLI at launch time.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
NETWORK_CONFIG_PATH = REPOSITORY_ROOT / "config" / "network.json"
TAILSCALE_HOSTNAME_ENV = "SMAI_TAILSCALE_HOSTNAME"
MAIN_APPLICATION_PORT_ENV = "SMAI_MAIN_PORT"
MAIN_APPLICATION_SCHEME_ENV = "SMAI_MAIN_SCHEME"
ANALYTICS_PORT_ENV = "SMAI_ANALYTICS_PORT"
ANALYTICS_SCHEME_ENV = "SMAI_ANALYTICS_SCHEME"
_HOSTNAME_LABEL_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


class NetworkConfigurationError(ValueError):
    """Raised when a safe Analytics URL cannot be built from configuration."""


@dataclass(frozen=True, slots=True)
class ApplicationEndpoint:
    scheme: str
    port: int


@dataclass(frozen=True, slots=True)
class NetworkSettings:
    tailscale_hostname: str
    main_application: ApplicationEndpoint
    server_analytics: ApplicationEndpoint


@dataclass(frozen=True, slots=True)
class NetworkURLs:
    """Normal MagicDNS URLs plus the server-local Analytics confirmation URL."""

    hostname: str
    main_application_url: str
    server_analytics_url: str
    analytics_local_url: str


def build_server_analytics_url(hostname: str, port: int, scheme: str = "http") -> str:
    """Build the sole user-facing Analytics URL from MagicDNS configuration."""

    return f"{_validate_scheme(scheme)}://{_validate_hostname(hostname)}:{_validate_port(port)}"


def build_main_application_url(hostname: str, port: int, scheme: str = "http") -> str:
    """Build the distinct Main Application URL without mixing its port with Analytics."""

    return f"{_validate_scheme(scheme)}://{_validate_hostname(hostname)}:{_validate_port(port)}"


def build_local_analytics_url(port: int, scheme: str = "http") -> str:
    """Build the localhost-only URL used for server-side confirmation."""

    return f"{_validate_scheme(scheme)}://localhost:{_validate_port(port)}"


def load_network_settings(
    *,
    config_path: Path = NETWORK_CONFIG_PATH,
    environ: Mapping[str, str] | None = None,
) -> NetworkSettings:
    """Load validated, non-secret settings with explicit environment overrides.

    The file is intentionally independent from the Main Application's internal
    configuration module. Updating the device name must update both projects
    (or set ``SMAI_TAILSCALE_HOSTNAME`` for both launchers).
    """

    values = os.environ if environ is None else environ
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        raise NetworkConfigurationError("Analyticsのnetwork.jsonを読み取れません。") from exc
    if not isinstance(raw, dict):
        raise NetworkConfigurationError("Analyticsのnetwork.jsonにnetwork設定がありません。")
    network = raw.get("network")
    if not isinstance(network, dict):
        network = migrate_legacy_network_settings(raw)

    main = _endpoint_from_mapping(network.get("main_application"), "Main Application")
    analytics = _endpoint_from_mapping(network.get("server_analytics"), "Server Analytics")
    hostname = values.get(TAILSCALE_HOSTNAME_ENV, network.get("tailscale_hostname"))
    settings = NetworkSettings(
        tailscale_hostname=_validate_hostname(hostname),
        main_application=ApplicationEndpoint(
            scheme=_validate_scheme(values.get(MAIN_APPLICATION_SCHEME_ENV, main.scheme)),
            port=_validate_port(values.get(MAIN_APPLICATION_PORT_ENV, main.port)),
        ),
        server_analytics=ApplicationEndpoint(
            scheme=_validate_scheme(values.get(ANALYTICS_SCHEME_ENV, analytics.scheme)),
            port=_validate_port(values.get(ANALYTICS_PORT_ENV, analytics.port)),
        ),
    )
    if settings.main_application.port == settings.server_analytics.port:
        raise NetworkConfigurationError("Main ApplicationとServer Analyticsのportは重複できません。")
    return settings


def migrate_legacy_network_settings(value: Mapping[str, object]) -> dict[str, object]:
    """Read former flat settings as a non-persisting compatibility migration.

    Earlier launchers derived a LAN address at start-up and had no versioned URL
    configuration. A flat transition configuration is accepted here, but the
    launcher never displays a LAN or Tailscale IP address.
    """

    hostname = value.get("tailscale_hostname")
    analytics_port = value.get("analytics_port")
    main_port = value.get("main_application_port")
    if hostname is None or analytics_port is None or main_port is None:
        raise NetworkConfigurationError("Analyticsのnetwork.jsonにnetwork設定がありません。")
    return {
        "tailscale_hostname": hostname,
        "main_application": {
            "scheme": value.get("main_application_scheme", "http"),
            "port": main_port,
        },
        "server_analytics": {
            "scheme": value.get("analytics_scheme", "http"),
            "port": analytics_port,
        },
    }


def resolve_network_urls(settings: NetworkSettings | None = None) -> NetworkURLs:
    """Resolve the two MagicDNS URLs and the server-local Analytics URL."""

    resolved = settings or load_network_settings()
    return NetworkURLs(
        hostname=resolved.tailscale_hostname,
        main_application_url=build_main_application_url(
            resolved.tailscale_hostname,
            resolved.main_application.port,
            resolved.main_application.scheme,
        ),
        server_analytics_url=build_server_analytics_url(
            resolved.tailscale_hostname,
            resolved.server_analytics.port,
            resolved.server_analytics.scheme,
        ),
        analytics_local_url=build_local_analytics_url(
            resolved.server_analytics.port,
            resolved.server_analytics.scheme,
        ),
    )


def _endpoint_from_mapping(value: object, label: str) -> ApplicationEndpoint:
    if not isinstance(value, dict):
        raise NetworkConfigurationError(f"{label}の設定がありません。")
    return ApplicationEndpoint(
        scheme=_validate_scheme(value.get("scheme")),
        port=_validate_port(value.get("port")),
    )


def _validate_scheme(value: object) -> str:
    scheme = str(value or "").strip().lower()
    if scheme != "http":
        raise NetworkConfigurationError("Analyticsのschemeはhttpだけを使用できます。")
    return scheme


def _validate_port(value: object) -> int:
    try:
        port = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise NetworkConfigurationError("portは1〜65535の整数で指定してください。") from exc
    if not 1 <= port <= 65535:
        raise NetworkConfigurationError("portは1〜65535の整数で指定してください。")
    return port


def _validate_hostname(value: object) -> str:
    hostname = str(value or "").strip().rstrip(".").lower()
    if not hostname:
        raise NetworkConfigurationError("MagicDNSホスト名が空です。")
    if hostname in {"localhost", "0.0.0.0"}:
        raise NetworkConfigurationError("MagicDNSホスト名にlocalhostまたは0.0.0.0は使用できません。")
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        raise NetworkConfigurationError("MagicDNSホスト名にIPアドレスは使用できません。")
    labels = hostname.split(".")
    if len(hostname) > 253 or any(not _HOSTNAME_LABEL_PATTERN.fullmatch(label) for label in labels):
        raise NetworkConfigurationError("MagicDNSホスト名は有効なDNS名で指定してください。")
    return hostname


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Resolve SMAI Server Analytics URLs.")
    parser.add_argument("--emit-batch", action="store_true", help="Emit validated Windows batch SET commands.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        settings = load_network_settings()
        urls = resolve_network_urls(settings)
    except NetworkConfigurationError as exc:
        print(f"[SMAI Server Analytics] {exc}", file=sys.stderr)
        return 2
    if args.emit_batch:
        print(f'set "SMAI_TAILSCALE_HOSTNAME={urls.hostname}"')
        print(f'set "SMAI_MAIN_PORT={settings.main_application.port}"')
        print(f'set "SMAI_MAIN_APPLICATION_URL={urls.main_application_url}"')
        print(f'set "SMAI_ANALYTICS_PORT={settings.server_analytics.port}"')
        print(f'set "SMAI_ANALYTICS_SCHEME={settings.server_analytics.scheme}"')
        print(f'set "SMAI_SERVER_ANALYTICS_URL={urls.server_analytics_url}"')
        print(f'set "SMAI_LOCAL_ANALYTICS_URL={urls.analytics_local_url}"')
        return 0
    print(urls.server_analytics_url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
