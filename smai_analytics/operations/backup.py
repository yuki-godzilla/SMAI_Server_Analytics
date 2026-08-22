from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from datetime import UTC, datetime
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


def _new_backup_destination() -> Path:
    """Create a unique backup directory without mixing two same-second runs."""

    backups_root = RUNTIME_ROOT / "backups"
    backups_root.mkdir(parents=True, exist_ok=True)
    stem = f"smai_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    for sequence in range(1000):
        suffix = "" if sequence == 0 else f"_{sequence:02d}"
        destination = backups_root / f"{stem}{suffix}"
        try:
            destination.mkdir()
            return destination
        except FileExistsError:
            continue
    raise OSError("could not allocate a unique backup directory")


def create() -> Path:
    destination = _new_backup_destination()
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
    (destination / "manifest.json").write_text(json.dumps({"created_at": datetime.now(UTC).isoformat(), "files": manifest}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
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


def verify_restored(path: Path, destination: Path) -> bool:
    """Confirm that an isolated restore contains every manifest file unchanged."""

    entries = _verified_entries(path)
    if entries is None:
        return False
    destination = destination.resolve()
    for item, _source in entries:
        target = _contained_path(destination, item.get("path"))
        digest = item.get("sha256")
        if target is None or not isinstance(digest, str):
            return False
        try:
            if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != digest.lower():
                return False
        except OSError:
            return False
    return True


def smoke_state_path() -> Path:
    """Return the latest local record for an isolated restore smoke check."""

    return RUNTIME_ROOT / "backup_restore_smoke.json"


def _write_smoke_result(result: dict[str, object]) -> bool:
    """Atomically retain the latest result and append an operations log line."""

    state_path = smoke_state_path()
    temporary_state = state_path.with_name(f"{state_path.name}.{os.getpid()}.tmp")
    log_path = RUNTIME_ROOT / "logs" / "backup_restore_smoke.log"
    serialized = json.dumps(result, ensure_ascii=False, sort_keys=True)
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as stream:
            stream.write(serialized + "\n")
        temporary_state.write_text(serialized + "\n", encoding="utf-8")
        temporary_state.replace(state_path)
        return True
    except OSError:
        try:
            temporary_state.unlink(missing_ok=True)
        except OSError:
            pass
        return False


def restore_smoke() -> dict[str, object]:
    """Create, verify, and hash-check an isolated restore without touching SMAI data."""

    result: dict[str, object] = {
        "checked_at": datetime.now(UTC).isoformat(),
        "overall": "critical",
        "backup_path": "",
        "detail": "backup restore smoke did not complete",
    }
    try:
        backup_path = create()
        result["backup_path"] = str(backup_path)
        if not verify(backup_path):
            result["detail"] = "created backup failed manifest verification"
        else:
            RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="smai-restore-smoke-", dir=str(RUNTIME_ROOT)) as directory:
                isolated_destination = Path(directory)
                if not restore(backup_path, isolated_destination):
                    result["detail"] = "isolated restore failed"
                elif not verify_restored(backup_path, isolated_destination):
                    result["detail"] = "isolated restore hash verification failed"
                else:
                    result["overall"] = "healthy"
                    result["detail"] = "created backup, isolated restore, and hash verification succeeded"
    except OSError as exc:
        result["detail"] = f"backup restore smoke failed: {type(exc).__name__}"

    if not _write_smoke_result(result):
        result["overall"] = "critical"
        result["detail"] = "backup restore smoke result could not be recorded"
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("create", "verify", "restore", "smoke"))
    parser.add_argument("path", nargs="?", type=Path)
    parser.add_argument("--destination", type=Path, help="Restore destination (defaults to the SMAI project root).")
    args = parser.parse_args()
    if args.command == "create":
        destination = create()
        print(destination)
        return 0 if verify(destination) else 1
    if args.command == "restore":
        return 0 if args.path and restore(args.path, args.destination) else 1
    if args.command == "smoke":
        result = restore_smoke()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["overall"] == "healthy" else 1
    return 0 if args.path and verify(args.path) else 1


if __name__ == "__main__":
    raise SystemExit(main())
