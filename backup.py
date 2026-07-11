from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(os.environ.get("SMAI_PROJECT_ROOT", r"C:\Users\user\workspace\SMAI_Projects\Smart_Market_AI"))
RUNTIME_ROOT = Path(os.environ.get("SMAI_RUNTIME_ROOT", r"C:\Users\user\workspace\SMAI_Projects\SMAI_Server_Runtime"))
SOURCES = (PROJECT_ROOT / "data/user", PROJECT_ROOT / "data/ops", PROJECT_ROOT / "data/marketdata/symbol_universe.csv")


def _source_files() -> list[Path]:
    result: list[Path] = []
    for source in SOURCES:
        if source.is_file():
            result.append(source)
        elif source.is_dir():
            result.extend(path for path in source.rglob("*") if path.is_file())
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
        manifest.append({"path": relative.as_posix(), "status": "ok", "sha256": hashlib.sha256(source.read_bytes()).hexdigest()})
    (destination / "manifest.json").write_text(json.dumps({"created_at": datetime.now().isoformat(), "files": manifest}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return destination


def verify(path: Path) -> bool:
    payload = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    for item in payload.get("files", []):
        if item.get("status") == "skipped":
            return False
        if not (path / item["path"]).exists():
            return False
        if hashlib.sha256((path / item["path"]).read_bytes()).hexdigest() != item["sha256"]:
            return False
    return True


def restore(path: Path) -> bool:
    manifest_path = path / "manifest.json"
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    for item in payload.get("files", []):
        if item.get("status") != "ok":
            continue
        source = path / item["path"]
        target = PROJECT_ROOT / item["path"]
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
    args = parser.parse_args()
    if args.command == "create":
        print(create())
        return 0
    if args.command == "restore":
        return 0 if args.path and restore(args.path) else 1
    return 0 if args.path and verify(args.path) else 1


if __name__ == "__main__":
    raise SystemExit(main())

