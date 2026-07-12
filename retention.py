from __future__ import annotations

import argparse
import json
import os
import shutil
import time
from pathlib import Path

RUNTIME_ROOT = Path(os.environ.get("SMAI_RUNTIME_ROOT", r"C:\Users\user\workspace\SMAI_Projects\SMAI_Server_Runtime"))
POLICY = Path(__file__).with_name("retention_policy.json")


def _expired_files(root: Path, cutoff: float) -> list[Path]:
    if not root.is_dir():
        return []
    return [path for path in root.rglob("*") if path.is_file() and path.stat().st_mtime < cutoff]


def _expired_backups(root: Path, cutoff: float) -> list[Path]:
    """Select only complete, tool-created backup directories for deletion."""

    backups = root / "backups"
    if not backups.is_dir():
        return []
    return [
        path
        for path in backups.iterdir()
        if path.is_dir()
        and path.name.startswith("smai_")
        and (path / "manifest.json").is_file()
        and path.stat().st_mtime < cutoff
    ]


def retention_candidates(runtime_root: Path, policy: dict[str, object], *, now: float | None = None) -> dict[str, list[Path]]:
    now = time.time() if now is None else now
    log_cutoff = now - int(policy["log_days"]) * 86400
    raw_health_cutoff = now - int(policy.get("health_raw_days", policy["log_days"])) * 86400
    backup_cutoff = now - int(policy["backup_days"]) * 86400
    raw_health_root = runtime_root / "logs" / "health"
    logs = [path for path in _expired_files(runtime_root / "logs", log_cutoff) if not path.is_relative_to(raw_health_root)]
    # The 5-second raw stream is useful for a recent incident, while the
    # compact telemetry rollups provide the longer visual history.
    logs.extend(_expired_files(raw_health_root, raw_health_cutoff))
    logs.extend(_expired_files(runtime_root / "metrics" / "health", log_cutoff))
    logs.extend(_expired_files(runtime_root / "metrics" / "tasks", log_cutoff))
    unique_logs = sorted(set(logs))
    return {
        "logs": unique_logs,
        "backups": _expired_backups(runtime_root, backup_cutoff),
    }


def apply_retention(candidates: dict[str, list[Path]], *, dry_run: bool = False) -> dict[str, int]:
    removed = {kind: 0 for kind in candidates}
    if dry_run:
        return removed
    for kind, paths in candidates.items():
        for path in paths:
            try:
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
                removed[kind] += 1
            except OSError:
                continue
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply local SMAI Runtime retention policy.")
    parser.add_argument("--dry-run", action="store_true", help="List eligible runtime files without deleting them.")
    args = parser.parse_args()
    try:
        policy = json.loads(POLICY.read_text(encoding="utf-8"))
        if not isinstance(policy, dict):
            raise ValueError("policy must be an object")
        candidates = retention_candidates(RUNTIME_ROOT, policy)
    except (OSError, ValueError, TypeError, KeyError):
        print("[SMAI] retention policy unavailable; no files removed")
        return 1

    if args.dry_run:
        for kind, paths in candidates.items():
            for path in paths:
                print(f"[SMAI] would remove {kind}: {path}")
        print(f"[SMAI] dry run: logs={len(candidates['logs'])}, backups={len(candidates['backups'])}")
        return 0

    removed = apply_retention(candidates)
    print(f"[SMAI] removed expired runtime logs={removed['logs']}, backups={removed['backups']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
