from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(os.environ.get("SMAI_PROJECT_ROOT", r"C:\Users\user\workspace\SMAI_Projects\Smart_Market_AI"))
RUNTIME_ROOT = Path(os.environ.get("SMAI_RUNTIME_ROOT", r"C:\Users\user\workspace\SMAI_Projects\SMAI_Server_Runtime"))
SOURCES = (PROJECT_ROOT / "data/user", PROJECT_ROOT / "data/ops", PROJECT_ROOT / "data/marketdata/symbol_universe.csv")


def _is_backup_file(path: Path) -> bool:
    """Exclude transient probes, locks, and in-progress atomic-write files."""

    return path.is_file() and path.suffix.lower() not in {".tmp", ".lock"}


def _source_files() -> list[Path]:
    result: list[Path] = []
    for source in SOURCES:
        if source.is_file():
            if _is_backup_file(source):
                result.append(source)
        elif source.is_dir():
            result.extend(path for path in source.rglob("*") if _is_backup_file(path))
    return sorted(result)


def create() -> Path:
    destination = RUNTIME_ROOT / "backups" / f"smai_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    destination.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, str]] = []
    for source in _source_files():
        relative = source.relative_to(PROJECT_ROOT)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(source, target)
        except OSError as exc:
            manifest.append({"path": relative.as_posix(), "status": "skipped", "error": str(exc)})
            continue
        manifest.append({"path": relative.as_posix(), "status": "ok", "sha256": hashlib.sha256(target.read_bytes()).hexdigest()})
    (destination / "manifest.json").write_text(json.dumps({"created_at": datetime.now().isoformat(), "files": manifest}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return destination


def _load_manifest(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    return payload if isinstance(payload, dict) else None


def _contained_path(root: Path, relative: object) -> Path | None:
    """Resolve a manifest path and reject absolute or escaping paths."""

    if not isinstance(relative, str) or not relative.strip():
        return None
    candidate = Path(relative)
    if candidate.is_absolute() or candidate.drive:
        return None
    root = root.resolve()
    resolved = (root / candidate).resolve()
    if resolved != root and root not in resolved.parents:
        return None
    return resolved


def _verified_entries(path: Path) -> list[tuple[dict[str, Any], Path]] | None:
    payload = _load_manifest(path)
    if payload is None or not isinstance(payload.get("files"), list):
        return None

    entries: list[tuple[dict[str, Any], Path]] = []
    for item in payload["files"]:
        if not isinstance(item, dict) or item.get("status") != "ok":
            return None
        source = _contained_path(path, item.get("path"))
        digest = item.get("sha256")
        if source is None or not isinstance(digest, str) or len(digest) != 64:
            return None
        if any(character not in "0123456789abcdef" for character in digest.lower()):
            return None
        try:
            if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != digest.lower():
                return None
        except OSError:
            return None
        entries.append((item, source))
    return entries


def verify(path: Path) -> bool:
    return _verified_entries(path) is not None


def restore(path: Path, destination: Path | None = None) -> bool:
    """Restore only a complete, hash-verified backup into a contained target."""

    entries = _verified_entries(path)
    if entries is None:
        return False
    destination = (destination or PROJECT_ROOT).resolve()
    targets: list[tuple[Path, Path]] = []
    for item, source in entries:
        target = _contained_path(destination, item.get("path"))
        if target is None:
            return False
        targets.append((source, target))

    # Validate every source and target before changing any destination file.
    for source, target in targets:
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(source, target)
        except OSError:
            return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("create", "verify", "restore"))
    parser.add_argument("path", nargs="?", type=Path)
    parser.add_argument("--destination", type=Path, help="Restore destination (defaults to the SMAI project root).")
    args = parser.parse_args()
    if args.command == "create":
        destination = create()
        print(destination)
        return 0 if verify(destination) else 1
    if args.command == "restore":
        return 0 if args.path and restore(args.path, args.destination) else 1
    return 0 if args.path and verify(args.path) else 1


if __name__ == "__main__":
    raise SystemExit(main())
