"""Record SMAI scheduled-task status without requiring an open browser session."""

from __future__ import annotations

import json

from smai_analytics.monitoring import task_observer


def main() -> int:
    rows = task_observer.collect_rows()
    print(json.dumps({"observed": len(rows)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
