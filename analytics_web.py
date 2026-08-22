"""Compatibility entry point for the browser-based SMAI Analytics console."""

import sys

from smai_analytics.ui import web_dashboard as _implementation


# The runtime lifecycle belongs to the SMAI server, while the large dashboard
# module stays read-only.  Register the two expected transition states here so
# a normal boot/shutdown is never rendered as a critical 18/100 incident.
_implementation.STATUS_PRIORITY.update({"starting": 2, "stopping": 2})
_implementation.STATUS_LABELS.update({"starting": "準備中", "stopping": "停止処理中"})
_implementation.STATUS_COLORS.update({"starting": "#38BDF8", "stopping": "#AAB8C8"})

_original_health_score = _implementation.health_score
_original_narrative = _implementation._narrative
_original_next_check = _implementation._next_check


def _lifecycle_health_score(overall: object) -> int:
    normalized = str(overall or "").casefold()
    if normalized == "starting":
        return 55
    if normalized == "stopping":
        return 45
    return _original_health_score(overall)


def _lifecycle_narrative(overall: str) -> tuple[str, str]:
    if overall == "starting":
        return "SMAIを準備中", "本体サービスの起動完了を待っています。起動猶予中は障害として扱いません。"
    if overall == "stopping":
        return "SMAIを停止処理中", "明示された停止・再起動処理の完了を待っています。"
    return _original_narrative(overall)


def _lifecycle_next_check(data):
    overall = str(data.get("overall") or "unknown").casefold()
    if overall == "starting":
        return "ダッシュボード", "本体SMAIの起動完了を待っています。", "準備完了後に自動で再評価"
    if overall == "stopping":
        return "ダッシュボード", "本体SMAIの停止・再起動処理中です。", "処理完了後に自動で再評価"
    return _original_next_check(data)


_implementation.health_score = _lifecycle_health_score
_implementation._narrative = _lifecycle_narrative
_implementation._next_check = _lifecycle_next_check

if __name__ == "__main__":
    _implementation.main()
else:
    sys.modules[__name__] = _implementation
