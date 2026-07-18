"""Shared, scheduler-driven task observations for the local Operations Console."""

from __future__ import annotations

import json
import os
from pathlib import Path

from . import task_monitor

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = Path(os.environ.get("SMAI_PROJECT_ROOT", r"C:\Users\user\workspace\SMAI_Projects\Smart_Market_AI"))
RUNTIME_ROOT = Path(os.environ.get("SMAI_RUNTIME_ROOT", r"C:\Users\user\workspace\SMAI_Projects\SMAI_Server_Runtime"))
BACKUP_SMOKE_STATE = RUNTIME_ROOT / "backup_restore_smoke.json"
AUTOFIX_CONFIG = REPOSITORY_ROOT / "config" / "codex_autofix.json"

_ANALYTICS_TASKS = {
    "SMAI-Host-Monitor",
    "SMAI-Host-Maintenance",
    "SMAI-Runtime-Retention",
    "SMAI-Incident-Automation",
    "SMAI-Codex-Autofix-Worker",
    "SMAI-Codex-Autofix-Deploy",
}


def _read_json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def task_names() -> tuple[str, ...]:
    """Return only enabled optional executor tasks; all core checks stay visible."""

    config = _read_json(AUTOFIX_CONFIG)
    active = config.get("enabled") is True and config.get("mode") == "active"
    deployment_enabled = active and config.get("deployment_enabled") is True
    return (
        "SMAI-Host-Monitor",
        "SMAI-Host-Maintenance",
        "SMAI-Runtime-Retention",
        "SmartMarketAI-Server-Autostart",
        "SmartMarketAI-Server-Watch",
        "SmartMarketAI-Symbol-Maintenance-IfDue",
        "SMAI-Incident-Automation",
    ) + (("SMAI-Codex-Autofix-Worker",) if active else ()) + (("SMAI-Codex-Autofix-Deploy",) if deployment_enabled else ())


def expected_task_root(task: str) -> Path:
    return REPOSITORY_ROOT if task in _ANALYTICS_TASKS else PROJECT_ROOT


def collect_rows() -> list[dict[str, str]]:
    """Collect and durably record scheduler metadata without exposing commands."""

    return task_monitor.collect(
        task_names(),
        runtime_root=RUNTIME_ROOT,
        expected_root=expected_task_root,
        backup_state=_read_json(BACKUP_SMOKE_STATE),
    )
