"""Durable, fail-closed Windows Task Scheduler observations for Analytics."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Callable, Iterable, Mapping

SCHEMA_VERSION = 1
OBSERVATION_INTERVAL = timedelta(minutes=5)
METRICS_DIRECTORY = "metrics"
TASK_HISTORY_DIRECTORY = "tasks"
STATE_NAME = "task_monitor_state.json"

# Logon/startup tasks have no recurring execution promise.  Their last result
# remains important, but an old last-run timestamp is not itself an incident.
FRESHNESS_POLICIES: dict[str, tuple[timedelta | None, timedelta | None]] = {
    "SMAI-Incident-Automation": (timedelta(minutes=10), timedelta(minutes=20)),
    "Backup Restore Smoke": (timedelta(days=31), timedelta(days=35)),
}


def parse_timestamp(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text or text.casefold() in {"n/a", "never", "not available", "なし", "利用不可"}:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
    except ValueError:
        pass
    for pattern in ("%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%m/%d/%Y %H:%M:%S"):
        try:
            local_zone = datetime.now().astimezone().tzinfo or UTC
            return datetime.strptime(text, pattern).replace(tzinfo=local_zone).astimezone(UTC)
        except ValueError:
            continue
    return None


def scheduler_values(output: str) -> dict[str, str]:
    """Parse LIST output while preserving only task metadata, never commands."""

    values: dict[str, str] = {}
    aliases = {
        "status": "status",
        "状態": "status",
        "last run time": "last_run_time",
        "前回の実行時刻": "last_run_time",
        "last result": "last_result",
        "前回の結果": "last_result",
        "next run time": "next_run_time",
        "次回の実行時刻": "next_run_time",
        "scheduled task state": "scheduled_state",
        "スケジュールされたタスクの状態": "scheduled_state",
    }
    for line in output.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        normalized = aliases.get(key.strip().casefold())
        if normalized:
            values[normalized] = value.strip()[:160]
    return values


def result_code(value: object) -> int | None:
    text = str(value or "").strip().casefold()
    if text in {"0", "0x0", "the operation completed successfully.", "success", "成功"}:
        return 0
    try:
        return int(text, 0)
    except ValueError:
        return None


def _age_status(name: str, last_run_at: object, *, now: datetime) -> tuple[str, str]:
    degraded_after, critical_after = FRESHNESS_POLICIES.get(name, (None, None))
    if degraded_after is None or critical_after is None:
        if parse_timestamp(last_run_at) is None:
            return "unknown", "最終実行時刻を取得できません"
        return "healthy", "起動契機タスク（最終実行を確認）"
    last_run = parse_timestamp(last_run_at)
    if last_run is None:
        return "unknown", "最終実行時刻を取得できません"
    age = max(timedelta(), now - last_run)
    if age > critical_after:
        return "critical", f"最終成功から {int(age.total_seconds() // 60)}分経過（期限超過）"
    if age > degraded_after:
        return "degraded", f"最終成功から {int(age.total_seconds() // 60)}分経過（確認が必要）"
    return "healthy", "予定内"


def classify_task(
    name: str,
    values: Mapping[str, object],
    *,
    path_ok: bool,
    now: datetime | None = None,
) -> tuple[str, str]:
    """Classify one scheduler record without inferring success from absence."""

    current = (now or datetime.now(UTC)).astimezone(UTC)
    code = result_code(values.get("last_result"))
    if code is not None and code != 0:
        detail = f"最終結果が失敗です（exit {code}）"
        if not path_ok:
            detail += " / 実行パスが現在のワークスペースと一致しません"
        return "critical", detail
    if values.get("last_result") and code is None:
        return "unknown", "最終結果を解釈できません"
    if not path_ok:
        return "degraded", "実行パスが現在のワークスペースと一致しません"
    state = str(values.get("scheduled_state") or values.get("status") or "").casefold()
    if state in {"disabled", "無効"}:
        return "degraded", "タスクが無効です"
    return _age_status(name, values.get("last_run_time"), now=current)


def _safe_text(value: object, *, limit: int = 240) -> str:
    return str(value or "").replace("\r", " ").replace("\n", " ").strip()[:limit]


def _task_row(
    name: str,
    values: Mapping[str, object],
    *,
    path_ok: bool,
    now: datetime,
    source: str = "scheduler",
) -> dict[str, str]:
    status, detail = classify_task(name, values, path_ok=path_ok, now=now)
    return {
        "name": name,
        "status": status,
        "last_run_at": _safe_text(values.get("last_run_time"), limit=80),
        "next_run_at": _safe_text(values.get("next_run_time"), limit=80),
        "last_result": _safe_text(values.get("last_result"), limit=80),
        "detail": detail,
        "source": source,
    }


def query_task(
    name: str,
    *,
    expected_root: Path,
    runner: Callable[..., subprocess.CompletedProcess[object]] = subprocess.run,
    now: datetime | None = None,
) -> dict[str, str]:
    """Read scheduler metadata and verify the task XML points at this workspace."""

    current = (now or datetime.now(UTC)).astimezone(UTC)
    try:
        result = runner(
            ["schtasks.exe", "/Query", "/TN", f"\\{name}", "/FO", "LIST", "/V"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {
            "name": name,
            "status": "unknown",
            "last_run_at": "",
            "next_run_at": "",
            "last_result": "",
            "detail": "タスク情報を取得できません",
            "source": "scheduler",
        }
    stdout = str(result.stdout or "")
    if result.returncode != 0:
        return {
            "name": name,
            "status": "unknown",
            "last_run_at": "",
            "next_run_at": "",
            "last_result": "",
            "detail": "タスクが未登録、または取得できません",
            "source": "scheduler",
        }
    try:
        contract = runner(
            ["schtasks.exe", "/Query", "/TN", f"\\{name}", "/XML"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        contract = None
    if contract is None or contract.returncode != 0:
        return {
            "name": name,
            "status": "unknown",
            "last_run_at": "",
            "next_run_at": "",
            "last_result": "",
            "detail": "タスク実行パスを取得できません",
            "source": "scheduler",
        }
    expected = str(expected_root).replace("/", "\\").casefold()
    path_ok = expected in str(contract.stdout or "").replace("/", "\\").casefold()
    return _task_row(name, scheduler_values(stdout), path_ok=path_ok, now=current)


def backup_row(backup_state: Mapping[str, object], *, now: datetime | None = None) -> dict[str, str]:
    """Expose isolated restore verification as a pseudo scheduled job."""

    current = (now or datetime.now(UTC)).astimezone(UTC)
    overall = _safe_text(backup_state.get("overall"), limit=40).casefold()
    checked_at = _safe_text(backup_state.get("checked_at"), limit=80)
    if not backup_state:
        return {
            "name": "Backup Restore Smoke",
            "status": "unknown",
            "last_run_at": "",
            "next_run_at": "月次検証",
            "last_result": "",
            "detail": "隔離復元検証の記録がありません",
            "source": "backup",
        }
    if overall != "healthy":
        return {
            "name": "Backup Restore Smoke",
            "status": "critical" if overall in {"critical", "failed", "error"} else "unknown",
            "last_run_at": checked_at,
            "next_run_at": "月次検証",
            "last_result": overall.upper() or "UNKNOWN",
            "detail": _safe_text(backup_state.get("detail"), limit=180) or "復元検証が成功していません",
            "source": "backup",
        }
    status, detail = _age_status("Backup Restore Smoke", checked_at, now=current)
    return {
        "name": "Backup Restore Smoke",
        "status": status,
        "last_run_at": checked_at,
        "next_run_at": "月次検証",
        "last_result": "HEALTHY",
        "detail": detail,
        "source": "backup",
    }


def _state_path(runtime_root: Path) -> Path:
    return runtime_root / METRICS_DIRECTORY / STATE_NAME


def _history_path(runtime_root: Path, observed_at: datetime) -> Path:
    return runtime_root / METRICS_DIRECTORY / TASK_HISTORY_DIRECTORY / f"{observed_at:%Y-%m-%d}.jsonl"


def _read_json(path: Path) -> dict[str, object] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def _atomic_write(path: Path, value: Mapping[str, object]) -> bool:
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(path)
        return True
    except OSError:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        return False


def _append_jsonl(path: Path, value: Mapping[str, object]) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")
        return True
    except OSError:
        return False


def record_observation(rows: Iterable[Mapping[str, object]], runtime_root: Path, *, now: datetime | None = None) -> bool:
    """Append a bounded task snapshot only on a change or every five minutes."""

    observed_at = (now or datetime.now(UTC)).astimezone(UTC)
    safe_rows = [
        {
            "name": _safe_text(row.get("name"), limit=120),
            "status": _safe_text(row.get("status"), limit=40),
            "last_run_at": _safe_text(row.get("last_run_at"), limit=80),
            "next_run_at": _safe_text(row.get("next_run_at"), limit=80),
            "last_result": _safe_text(row.get("last_result"), limit=80),
            "detail": _safe_text(row.get("detail"), limit=240),
            "source": _safe_text(row.get("source"), limit=40),
        }
        for row in rows
    ]
    fingerprint = json.dumps(safe_rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    state = _read_json(_state_path(runtime_root)) or {}
    previous_at = parse_timestamp(state.get("observed_at"))
    changed = state.get("fingerprint") != fingerprint
    if previous_at is not None and not changed and observed_at - previous_at < OBSERVATION_INTERVAL:
        return True
    payload = {
        "schema_version": SCHEMA_VERSION,
        "observed_at": observed_at.isoformat(),
        "tasks": safe_rows,
    }
    if not _append_jsonl(_history_path(runtime_root, observed_at), payload):
        return False
    return _atomic_write(_state_path(runtime_root), {"schema_version": SCHEMA_VERSION, "observed_at": payload["observed_at"], "fingerprint": fingerprint})


def read_observations(
    runtime_root: Path,
    *,
    now: datetime | None = None,
    window: timedelta = timedelta(days=1),
) -> list[dict[str, object]]:
    current = (now or datetime.now(UTC)).astimezone(UTC)
    start = current - window
    directory = runtime_root / METRICS_DIRECTORY / TASK_HISTORY_DIRECTORY
    rows: list[dict[str, object]] = []
    if not directory.is_dir():
        return rows
    date = start.date()
    while date <= current.date():
        path = directory / f"{date:%Y-%m-%d}.jsonl"
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            lines = []
        for line in lines:
            try:
                value = json.loads(line)
            except (TypeError, ValueError):
                continue
            if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
                continue
            timestamp = parse_timestamp(value.get("observed_at"))
            tasks = value.get("tasks")
            if timestamp is not None and start <= timestamp <= current and isinstance(tasks, list):
                rows.append(value)
        date += timedelta(days=1)
    return sorted(rows, key=lambda row: str(row.get("observed_at", "")))


def collect(
    task_names: Iterable[str],
    *,
    runtime_root: Path,
    expected_root: Callable[[str], Path],
    backup_state: Mapping[str, object],
    runner: Callable[..., subprocess.CompletedProcess[object]] = subprocess.run,
    now: datetime | None = None,
) -> list[dict[str, str]]:
    current = (now or datetime.now(UTC)).astimezone(UTC)
    rows = [query_task(name, expected_root=expected_root(name), runner=runner, now=current) for name in task_names]
    rows.append(backup_row(backup_state, now=current))
    record_observation(rows, runtime_root, now=current)
    return rows
