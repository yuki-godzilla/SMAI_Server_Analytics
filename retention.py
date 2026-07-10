from __future__ import annotations

import json
import os
import time
from pathlib import Path

RUNTIME_ROOT = Path(os.environ.get("SMAI_RUNTIME_ROOT", r"C:\Users\user\workspace\SMAI_Projects\SMAI_Server_Runtime"))
POLICY = Path(__file__).with_name("retention_policy.json")


def main() -> int:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    cutoff = time.time() - int(policy["log_days"]) * 86400
    removed = 0
    for path in (RUNTIME_ROOT / "logs").glob("*"):
        if path.is_file() and path.stat().st_mtime < cutoff:
            path.unlink()
            removed += 1
    print(f"[SMAI] removed {removed} expired runtime logs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

