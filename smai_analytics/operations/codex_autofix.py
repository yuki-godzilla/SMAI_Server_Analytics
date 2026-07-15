"""Approval-gated Codex repair worker for isolated Analytics worktrees.

The worker is disabled by default.  It never edits Smart_Market_AI, pushes a
branch, restarts a service, or merges without a second administrator lease.
"""

from __future__ import annotations

import getpass
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Callable, Iterator, Mapping, Sequence

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_ROOT = Path(
    os.environ.get(
        "SMAI_RUNTIME_ROOT",
        r"C:\Users\user\workspace\SMAI_Projects\SMAI_Server_Runtime",
    )
)
INCIDENT_ROOT = RUNTIME_ROOT / "incident_operations"
REQUESTS_DIR = INCIDENT_ROOT / "codex_requests"
REPORTS_DIR = INCIDENT_ROOT / "reports"
AUTOFIX_ROOT = INCIDENT_ROOT / "autofix"
AUTOFIX_STATE_DIR = AUTOFIX_ROOT / "states"
AUTOFIX_RUNS_DIR = AUTOFIX_ROOT / "runs"
AUTOFIX_WORKTREES_DIR = AUTOFIX_ROOT / "worktrees"
AUTOFIX_INDEX_PATH = AUTOFIX_ROOT / "events.jsonl"
AUTOFIX_LOCK_PATH = AUTOFIX_ROOT / "worker.lock"
AUTOFIX_CONFIG_PATH = REPOSITORY_ROOT / "config" / "codex_autofix.json"

SCHEMA_VERSION = 3
APPROVAL_LIFETIME = timedelta(hours=24)
MERGE_APPROVAL_LIFETIME = timedelta(hours=1)
RUN_LIFETIME = timedelta(minutes=45)
CODEX_TIMEOUT_SECONDS = 45 * 60

_SENSITIVE_DIFF_PATTERNS = (
    re.compile(r"(?i)authorization\s*:\s*bearer\s+\S+"),
    re.compile(r"(?i)\b(?:api[_-]?key|token|secret|password)\s*[=:]\s*['\"]?[^\s'\"]+"),
    re.compile(r"\b(?:sk|ghp|github_pat)_[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"(?i)(?:[a-z]:\\Users\\|\\\\)[^\s\"'<>]+"),
)
_EMAIL_PATTERN = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_IP_PATTERN = re.compile(
    r"\b(?:10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|"
    r"172\.(?:1[6-9]|2\d|3[0-1])(?:\.\d{1,3}){2})\b"
)
_EXTERNAL_URL_PATTERN = re.compile(
    r"""(?i)https?://(?!(?:localhost|127\.0\.0\.1)(?::\d+)?(?:[/?#\s"'<>]|$))\S+"""
)


class AutofixError(RuntimeError):
    """A bounded, operator-safe Autofix failure."""

    def __init__(self, category: str, message: str) -> None:
        super().__init__(message)
        self.category = category


def utc_now() -> datetime:
    return datetime.now(UTC)


def _timestamp(value: datetime | None = None) -> str:
    return (value or utc_now()).isoformat()


def _parse_timestamp(value: object) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _safe_text(value: object, *, limit: int = 240) -> str:
    return str(value or "").replace("\r", " ").replace("\n", " ").strip()[:limit]


def _safe_request_id(value: object) -> str:
    candidate = _safe_text(value, limit=120)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,119}", candidate):
        raise ValueError("request_id is invalid")
    return candidate


def _load_json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


def _write_json_atomic(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _append_jsonl(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")


def _state_path(request_id: str) -> Path:
    return AUTOFIX_STATE_DIR / f"{_safe_request_id(request_id)}.json"


def _public_state(state: Mapping[str, object]) -> dict[str, object]:
    keys = (
        "schema_version",
        "request_id",
        "status",
        "attempt",
        "base_commit",
        "branch",
        "approved_at",
        "approval_expires_at",
        "run_started_at",
        "run_expires_at",
        "repair_commit",
        "diff_sha256",
        "merge_approved_at",
        "merge_expires_at",
        "merged_at",
        "failure_category",
        "needs_operator_visual_review",
        "updated_at",
    )
    return {key: state[key] for key in keys if key in state}


def _save_state(state: dict[str, object], *, event: str) -> dict[str, object]:
    state["schema_version"] = SCHEMA_VERSION
    state["updated_at"] = _timestamp()
    _write_json_atomic(_state_path(str(state["request_id"])), state)
    row = _public_state(state)
    row["event"] = event
    _append_jsonl(AUTOFIX_INDEX_PATH, row)
    return state


def load_config() -> dict[str, object]:
    """Return a fail-closed local Autofix configuration."""

    config = _load_json(AUTOFIX_CONFIG_PATH)
    enabled = config.get("enabled") is True
    mode = str(config.get("mode") or "dry_run").casefold()
    if mode not in {"dry_run", "active"}:
        mode = "dry_run"
        enabled = False
    return {
        "enabled": enabled,
        "mode": mode,
        "worker_interval_minutes": 5,
        "execution_limit_minutes": 45,
    }


def _run_process(
    args: Sequence[str],
    *,
    cwd: Path,
    timeout: int = 120,
    env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            list(args),
            cwd=cwd,
            env=dict(env) if env is not None else None,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        category = (
            "command_timeout"
            if isinstance(error, subprocess.TimeoutExpired)
            else "command_unavailable"
        )
        raise AutofixError(category, "A required local command could not complete.") from error
    if result.returncode != 0:
        raise AutofixError("command_failed", "A required local command returned a non-zero result.")
    return result


def _git(args: Sequence[str], *, cwd: Path = REPOSITORY_ROOT, timeout: int = 120) -> str:
    try:
        result = _run_process(["git", *args], cwd=cwd, timeout=timeout)
    except AutofixError as error:
        operation = next(
            (
                value
                for value in args
                if value in {"add", "commit", "diff", "merge", "rev-parse", "status", "worktree"}
            ),
            "command",
        )
        if operation == "diff" and "--binary" in args:
            operation = "diff_patch"
        elif operation == "diff" and "--cached" in args:
            operation = "diff_cached"
        raise AutofixError(f"git_{operation}_failed", "A required Git operation failed.") from error
    return result.stdout.strip()


def _head_commit(repository: Path = REPOSITORY_ROOT) -> str:
    value = _git(["rev-parse", "HEAD"], cwd=repository)
    if not re.fullmatch(r"[0-9a-fA-F]{40}", value):
        raise AutofixError("git_head_unavailable", "The Analytics HEAD commit is unavailable.")
    return value.lower()


def path_is_allowed(value: object) -> bool:
    """Return True only for the v1 Analytics repair allowlist."""

    normalized = str(value or "").replace("\\", "/").strip("/")
    path = PurePosixPath(normalized)
    parts = tuple(part.casefold() for part in path.parts)
    if not normalized or path.is_absolute() or ".." in parts or " -> " in normalized:
        return False
    if any(token in normalized.casefold() for token in ("credential", "secret")):
        return False
    if normalized in {"analytics_web.py", "README.md"}:
        return True
    if parts and parts[0] == "smai_analytics" and path.suffix.casefold() == ".py":
        return True
    if parts and parts[0] == "tests" and path.suffix.casefold() == ".py":
        return True
    return bool(parts and parts[0] == "documents" and path.suffix.casefold() == ".md")


def validate_changed_paths(paths: Sequence[str]) -> tuple[str, ...]:
    normalized = tuple(dict.fromkeys(str(path).replace("\\", "/") for path in paths))
    if not normalized:
        raise AutofixError("empty_diff", "Codex did not produce a repair diff.")
    rejected = [path for path in normalized if not path_is_allowed(path)]
    if rejected:
        raise AutofixError(
            "path_not_allowed", "The repair contains a path outside the Autofix allowlist."
        )
    return normalized


def validate_diff_text(diff_text: str) -> None:
    """Reject common secret and personal-data forms in a newly generated diff."""

    for pattern in _SENSITIVE_DIFF_PATTERNS:
        if pattern.search(diff_text):
            raise AutofixError("sensitive_diff", "The repair diff contains sensitive-looking data.")
    for address in _EMAIL_PATTERN.findall(diff_text):
        if not address.casefold().endswith(("@example.com", "@localhost.invalid")):
            raise AutofixError("sensitive_diff", "The repair diff contains an email address.")
    if _IP_PATTERN.search(diff_text):
        raise AutofixError("sensitive_diff", "The repair diff contains an internal IP address.")
    if _EXTERNAL_URL_PATTERN.search(diff_text):
        raise AutofixError("external_url_diff", "The repair diff contains an external URL.")


def _request_exists(request_id: str) -> bool:
    normalized = _safe_request_id(request_id)
    return (REQUESTS_DIR / f"{normalized}.md").is_file() and (
        REPORTS_DIR / f"{normalized}.md"
    ).is_file()


def _append_report_event(
    state: Mapping[str, object],
    *,
    status: str,
    summary: str,
    verification: str,
    notification_kind: str,
) -> None:
    from . import incident_automation

    incident_automation.record_improvement_report(
        request_id=str(state["request_id"]),
        status=status,
        summary=summary,
        verification=verification,
        notification_kind=notification_kind,
    )


def approve_autofix(
    *,
    request_id: str,
    now: datetime | None = None,
    repository: Path = REPOSITORY_ROOT,
) -> dict[str, object]:
    """Create a 24-hour repair lease for one known incident."""

    normalized = _safe_request_id(request_id)
    if not _request_exists(normalized):
        raise FileNotFoundError(f"unknown incident request: {normalized}")
    current = now or utc_now()
    existing = _load_json(_state_path(normalized))
    if existing.get("status") in {"autofix_approved", "autofix_running"}:
        expiry = _parse_timestamp(existing.get("approval_expires_at"))
        run_expiry = _parse_timestamp(existing.get("run_expires_at"))
        run_is_current = existing.get("status") != "autofix_running" or (
            run_expiry is not None and run_expiry > current
        )
        if expiry is not None and expiry > current and run_is_current:
            return _public_state(existing)
    if existing.get("status") in {
        "auto_patch_ready",
        "autofix_merge_approved",
        "auto_merged_pending_deploy",
    }:
        raise AutofixError("invalid_transition", "This incident already has a prepared repair.")
    attempt = int(existing.get("attempt") or 0) + 1
    base_commit = _head_commit(repository)
    state: dict[str, object] = {
        "request_id": normalized,
        "status": "autofix_approved",
        "attempt": attempt,
        "base_commit": base_commit,
        "branch": f"autofix/{normalized}-{attempt}",
        "approved_at": _timestamp(current),
        "approval_expires_at": _timestamp(current + APPROVAL_LIFETIME),
        "approval_source": "local_administrator_cli",
    }
    _save_state(state, event="autofix_approved")
    _append_report_event(
        state,
        status="autofix_approved",
        summary="Administrator approved an isolated Codex Autofix run.",
        verification=f"Base commit {base_commit[:12]}; approval expires in 24 hours.",
        notification_kind="autofix_approval",
    )
    return _public_state(state)


def cancel_autofix(
    *,
    request_id: str,
    reason: str,
    now: datetime | None = None,
) -> dict[str, object]:
    normalized = _safe_request_id(request_id)
    state = _load_json(_state_path(normalized))
    if not state:
        raise FileNotFoundError(f"unknown Autofix request: {normalized}")
    if state.get("status") == "auto_merged_pending_deploy":
        raise AutofixError("invalid_transition", "A merged repair cannot be cancelled.")
    if state.get("status") == "auto_cancelled":
        return _public_state(state)
    state["status"] = "auto_cancelled"
    state["cancelled_at"] = _timestamp(now)
    state["cancel_reason"] = _safe_text(reason, limit=240) or "administrator_cancelled"
    _save_state(state, event="auto_cancelled")
    _append_report_event(
        state,
        status="auto_cancelled",
        summary="Administrator cancelled the Codex Autofix request.",
        verification="No automatic merge is permitted for this lease.",
        notification_kind="autofix_cancelled",
    )
    return _public_state(state)


def autofix_status(*, request_id: str, now: datetime | None = None) -> dict[str, object]:
    normalized = _safe_request_id(request_id)
    state = _load_json(_state_path(normalized))
    if not state:
        return {"request_id": normalized, "status": "unknown"}
    current = now or utc_now()
    result = _public_state(state)
    if result.get("status") == "autofix_approved":
        expiry = _parse_timestamp(result.get("approval_expires_at"))
        if expiry is None or expiry <= current:
            result["status"] = "auto_blocked"
            result["failure_category"] = "approval_expired"
    if result.get("status") == "autofix_running":
        expiry = _parse_timestamp(result.get("run_expires_at"))
        if expiry is None or expiry <= current:
            result["status"] = "auto_blocked"
            result["failure_category"] = "run_lease_expired"
    if result.get("status") == "autofix_merge_approved":
        expiry = _parse_timestamp(result.get("merge_expires_at"))
        if expiry is None or expiry <= current:
            result["status"] = "auto_merge_blocked"
            result["failure_category"] = "merge_approval_expired"
    return result


def _result_schema(request_id: str, base_commit: str) -> dict[str, object]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {
            "request_id": {"const": request_id},
            "base_commit": {"const": base_commit},
            "status": {"enum": ["fixed", "blocked", "not_reproducible", "failed"]},
            "summary": {"type": "string", "maxLength": 1200},
            "changed_files": {"type": "array", "items": {"type": "string"}, "maxItems": 100},
            "verification": {"type": "array", "items": {"type": "string"}, "maxItems": 100},
            "needs_operator_visual_review": {"type": "boolean"},
        },
        "required": [
            "request_id",
            "base_commit",
            "status",
            "summary",
            "changed_files",
            "verification",
            "needs_operator_visual_review",
        ],
        "additionalProperties": False,
    }


def _work_order(state: Mapping[str, object]) -> str:
    request_id = str(state["request_id"])
    draft = (REQUESTS_DIR / f"{request_id}.md").read_text(encoding="utf-8")
    evidence = [line for line in draft.splitlines() if line.startswith("- ")][:20]
    return (
        "\n".join(
            [
                f"# SMAI Analytics Autofix work order: {request_id}",
                "",
                f"- Base commit: `{state['base_commit']}`",
                "- Scope: SMAI_Server_Analytics only",
                "- Output: one minimal repair in this isolated worktree",
                "",
                "## Bounded incident evidence",
                "",
                *evidence,
                "",
                "## Required boundaries",
                "",
                "1. Read AGENTS.md before editing.",
                "2. Do not access Smart_Market_AI source, Runtime user data, credentials, or the network.",
                "3. Change only allowlisted Analytics Python, tests, README, or Documents files.",
                "4. Do not install dependencies, restart processes, commit, push, or alter Windows settings.",
                "5. Reproduce the issue when possible and make the smallest deterministic repair.",
                "6. Report checks actually executed; request visual review when browser evidence is unavailable.",
            ]
        )
        + "\n"
    )


CodexRunner = Callable[[Path, Mapping[str, object], Path, Path], int]
Validator = Callable[[Path, str], Sequence[str]]


def _default_codex_runner(
    worktree: Path,
    state: Mapping[str, object],
    schema_path: Path,
    result_path: Path,
) -> int:
    prompt = (
        "Read .codex-autofix-work-order.md and complete only that repair. "
        "Return the required structured result."
    )
    run_dir = AUTOFIX_RUNS_DIR / str(state["request_id"])
    run_dir.mkdir(parents=True, exist_ok=True)
    events_path = run_dir / f"attempt-{state['attempt']}-events.jsonl"
    command = [
        "codex",
        "exec",
        "--ephemeral",
        "--ignore-user-config",
        "--sandbox",
        "workspace-write",
        "--cd",
        str(worktree),
        "--output-schema",
        str(schema_path),
        "--output-last-message",
        str(result_path),
        "--json",
        prompt,
    ]
    started = time.monotonic()
    with events_path.open("w", encoding="utf-8") as stdout:
        try:
            process = subprocess.Popen(
                command,
                cwd=worktree,
                text=True,
                stdout=stdout,
                stderr=subprocess.DEVNULL,
            )
        except OSError as error:
            raise AutofixError("codex_unavailable", "Codex could not be started.") from error
        while process.poll() is None:
            latest = _load_json(_state_path(str(state["request_id"])))
            if latest.get("status") == "auto_cancelled":
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                return 130
            if time.monotonic() - started > CODEX_TIMEOUT_SECONDS:
                process.kill()
                return 124
            time.sleep(2)
        return int(process.returncode or 0)


def _changed_paths(worktree: Path) -> tuple[str, ...]:
    output = _run_process(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=worktree,
    ).stdout.rstrip()
    paths: list[str] = []
    for line in output.splitlines():
        if len(line) < 4:
            continue
        value = line[3:].strip().strip('"')
        if " -> " in value:
            paths.extend(part.strip().strip('"') for part in value.split(" -> ", 1))
        else:
            paths.append(value)
    return validate_changed_paths(paths)


def _validation_commands() -> tuple[tuple[str, ...], ...]:
    return (
        (
            sys.executable,
            "-m",
            "py_compile",
            "analytics_web.py",
            "health.py",
            "backup.py",
            "retention.py",
        ),
        (sys.executable, "-m", "compileall", "-q", "smai_analytics"),
        (
            sys.executable,
            "-m",
            "unittest",
            "tests.test_analytics_web",
            "tests.test_web_operations",
            "tests.test_incident_automation",
            "tests.test_codex_autofix",
            "-v",
        ),
        (sys.executable, "tests/ui_web_render_sprint.py"),
    )


def _default_validator(worktree: Path, base_commit: str) -> Sequence[str]:
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["SMAI_ANALYTICS_TEST_SKIP_HEALTH_PROBE"] = "1"
    completed: list[str] = []
    _git(["diff", "--check"], cwd=worktree)
    for command in _validation_commands():
        _run_process(command, cwd=worktree, timeout=300, env=environment)
        completed.append(" ".join(command[1:3]))
    return completed


def _validate_result(
    result: Mapping[str, object],
    *,
    request_id: str,
    base_commit: str,
) -> None:
    expected_keys = {
        "request_id",
        "base_commit",
        "status",
        "summary",
        "changed_files",
        "verification",
        "needs_operator_visual_review",
    }
    if set(result) != expected_keys:
        raise AutofixError("result_schema", "The Codex result fields are invalid.")
    if result.get("request_id") != request_id or result.get("base_commit") != base_commit:
        raise AutofixError("result_mismatch", "The Codex result does not match its approval lease.")
    if result.get("status") not in {"fixed", "blocked", "not_reproducible", "failed"}:
        raise AutofixError("result_schema", "The Codex result status is invalid.")
    if not isinstance(result.get("summary"), str) or len(str(result["summary"])) > 1200:
        raise AutofixError("result_schema", "The Codex result summary is invalid.")
    changed_files = result.get("changed_files")
    verification = result.get("verification")
    if (
        not isinstance(changed_files, list)
        or len(changed_files) > 100
        or not all(isinstance(item, str) for item in changed_files)
        or not isinstance(verification, list)
        or len(verification) > 100
        or not all(isinstance(item, str) for item in verification)
    ):
        raise AutofixError("result_schema", "The Codex result shape is invalid.")
    if not isinstance(result.get("needs_operator_visual_review"), bool):
        raise AutofixError("result_schema", "The Codex visual-review field is invalid.")
    validate_diff_text(json.dumps(result, ensure_ascii=False, sort_keys=True))


def _prepare_worktree(state: Mapping[str, object], repository: Path) -> Path:
    request_id = str(state["request_id"])
    attempt = int(state.get("attempt") or 1)
    worktree = AUTOFIX_WORKTREES_DIR / f"{request_id}-{attempt}"
    if worktree.exists():
        raise AutofixError("worktree_exists", "The isolated Autofix worktree already exists.")
    worktree.parent.mkdir(parents=True, exist_ok=True)
    _git(
        [
            "worktree",
            "add",
            "-b",
            str(state["branch"]),
            str(worktree),
            str(state["base_commit"]),
        ],
        cwd=repository,
    )
    return worktree


def _record_failure(state: dict[str, object], error: AutofixError, *, merge: bool = False) -> None:
    if merge:
        status = "auto_merge_blocked"
    elif error.category.startswith("codex_") or error.category in {
        "result_mismatch",
        "result_schema",
    }:
        status = "auto_failed"
    elif error.category in {
        "approval_expired",
        "blocked",
        "not_reproducible",
        "worker_busy",
        "worktree_exists",
        "git_head_unavailable",
    }:
        status = "auto_blocked"
    elif error.category == "failed":
        status = "auto_failed"
    else:
        status = "auto_validation_failed"
    state["status"] = status
    state["failure_category"] = error.category
    _save_state(state, event=str(state["status"]))
    _append_report_event(
        state,
        status=str(state["status"]),
        summary="Codex Autofix stopped without reporting a successful deployment.",
        verification=error.category,
        notification_kind="autofix_failed",
    )


def execute_repair(
    state: dict[str, object],
    *,
    repository: Path = REPOSITORY_ROOT,
    now: datetime | None = None,
    codex_runner: CodexRunner = _default_codex_runner,
    validator: Validator = _default_validator,
) -> dict[str, object]:
    """Run one approved repair in an isolated worktree and create one local commit."""

    current = now or utc_now()
    try:
        expiry = _parse_timestamp(state.get("approval_expires_at"))
        if state.get("status") != "autofix_approved" or expiry is None or expiry <= current:
            raise AutofixError("approval_expired", "The Autofix approval is missing or expired.")
        state["status"] = "autofix_running"
        state["run_started_at"] = _timestamp(current)
        state["run_expires_at"] = _timestamp(current + RUN_LIFETIME)
        _save_state(state, event="autofix_running")
        worktree = _prepare_worktree(state, repository)
        order_path = worktree / ".codex-autofix-work-order.md"
        schema_path = worktree / ".codex-autofix-result-schema.json"
        result_path = worktree / ".codex-autofix-result.json"
        order_path.write_text(_work_order(state), encoding="utf-8")
        _write_json_atomic(
            schema_path, _result_schema(str(state["request_id"]), str(state["base_commit"]))
        )
        return_code = codex_runner(worktree, state, schema_path, result_path)
        if return_code != 0:
            category = (
                "codex_cancelled"
                if return_code == 130
                else "codex_timeout" if return_code == 124 else "codex_failed"
            )
            raise AutofixError(category, "Codex did not complete the approved repair.")
        result = _load_json(result_path)
        _validate_result(
            result,
            request_id=str(state["request_id"]),
            base_commit=str(state["base_commit"]),
        )
        run_dir = AUTOFIX_RUNS_DIR / str(state["request_id"])
        run_dir.mkdir(parents=True, exist_ok=True)
        _write_json_atomic(run_dir / f"attempt-{state['attempt']}-result.json", result)
        for artifact in (order_path, schema_path, result_path):
            artifact.unlink(missing_ok=True)
        latest = _load_json(_state_path(str(state["request_id"])))
        if latest.get("status") == "auto_cancelled":
            return _public_state(latest)
        if result.get("status") != "fixed":
            category = str(result.get("status") or "codex_blocked")
            raise AutofixError(category, "Codex did not produce a repair eligible for commit.")
        changed_paths = _changed_paths(worktree)
        reported_paths = validate_changed_paths([str(path) for path in result["changed_files"]])
        if set(changed_paths) != set(reported_paths):
            raise AutofixError(
                "changed_files_mismatch", "Codex did not report the exact repair paths."
            )
        _git(["add", "-N", "--", *changed_paths], cwd=worktree)
        diff_text = _git(
            ["diff", "--binary", "--no-ext-diff", str(state["base_commit"]), "--"],
            cwd=worktree,
        )
        validate_diff_text(diff_text)
        try:
            verification = list(validator(worktree, str(state["base_commit"])))
        except AutofixError:
            raise
        except Exception as error:
            raise AutofixError(
                "validation_failed", "The deterministic repair validation failed."
            ) from error
        _git(["add", "--", *changed_paths], cwd=worktree)
        _git(["diff", "--cached", "--check"], cwd=worktree)
        _git(
            [
                "-c",
                "user.name=SMAI Codex Autofix",
                "-c",
                "user.email=smai-autofix@localhost.invalid",
                "commit",
                "-m",
                f"fix: prepare verified Autofix for {state['request_id']}",
            ],
            cwd=worktree,
        )
        repair_commit = _head_commit(worktree)
        parent = _git(["rev-parse", f"{repair_commit}^"], cwd=worktree).lower()
        if parent != str(state["base_commit"]).lower():
            raise AutofixError(
                "commit_parent_mismatch", "The repair commit parent changed unexpectedly."
            )
        state["status"] = "auto_patch_ready"
        state["repair_commit"] = repair_commit
        state["diff_sha256"] = hashlib.sha256(diff_text.encode("utf-8")).hexdigest()
        state["changed_files"] = list(changed_paths)
        state["verification"] = verification
        state["needs_operator_visual_review"] = bool(result["needs_operator_visual_review"])
        state.pop("failure_category", None)
        _save_state(state, event="auto_patch_ready")
        _append_report_event(
            state,
            status="auto_patch_ready",
            summary=(
                f"Verified Autofix commit {repair_commit[:12]} is ready for administrator review; "
                f"{len(changed_paths)} file(s) changed."
            ),
            verification=(
                f"Diff SHA-256 {state['diff_sha256']}; deterministic checks passed; "
                f"visual review required={state['needs_operator_visual_review']}."
            ),
            notification_kind="autofix_ready",
        )
        return _public_state(state)
    except AutofixError as error:
        latest = _load_json(_state_path(str(state["request_id"])))
        if latest.get("status") == "auto_cancelled":
            return _public_state(latest)
        _record_failure(state, error)
        return _public_state(state)


def approve_autofix_merge(
    *,
    request_id: str,
    commit: str,
    now: datetime | None = None,
) -> dict[str, object]:
    normalized = _safe_request_id(request_id)
    state = _load_json(_state_path(normalized))
    expected = str(state.get("repair_commit") or "").lower()
    supplied = _safe_text(commit, limit=40).lower()
    if state.get("status") == "autofix_merge_approved" and supplied == expected:
        expiry = _parse_timestamp(state.get("merge_expires_at"))
        if expiry is not None and expiry > (now or utc_now()):
            return _public_state(state)
    if state.get("status") not in {"auto_patch_ready", "auto_merge_blocked"} or not re.fullmatch(
        r"[0-9a-f]{40}", supplied
    ):
        raise AutofixError(
            "invalid_transition", "No verified Autofix commit is ready for merge approval."
        )
    if supplied != expected:
        raise AutofixError(
            "commit_mismatch", "The administrator-approved commit does not match the repair report."
        )
    current = now or utc_now()
    state["status"] = "autofix_merge_approved"
    state["merge_approved_at"] = _timestamp(current)
    state["merge_expires_at"] = _timestamp(current + MERGE_APPROVAL_LIFETIME)
    state["merge_approval_source"] = "local_administrator_cli"
    _save_state(state, event="autofix_merge_approved")
    _append_report_event(
        state,
        status="autofix_merge_approved",
        summary=f"Administrator approved fast-forward merge of commit {supplied[:12]}.",
        verification="The one-time merge lease expires in one hour.",
        notification_kind="autofix_merge_approval",
    )
    return _public_state(state)


def execute_merge(
    state: dict[str, object],
    *,
    repository: Path = REPOSITORY_ROOT,
    now: datetime | None = None,
    validator: Validator = _default_validator,
) -> dict[str, object]:
    """Fast-forward one exact approved repair commit into a clean local checkout."""

    current = now or utc_now()
    try:
        expiry = _parse_timestamp(state.get("merge_expires_at"))
        if state.get("status") != "autofix_merge_approved" or expiry is None or expiry <= current:
            raise AutofixError(
                "merge_approval_expired", "The merge approval is missing or expired."
            )
        status = _git(["status", "--porcelain=v1", "--untracked-files=all"], cwd=repository)
        if status:
            raise AutofixError("target_dirty", "The Analytics checkout is not clean.")
        base_commit = str(state.get("base_commit") or "").lower()
        repair_commit = str(state.get("repair_commit") or "").lower()
        if _head_commit(repository) != base_commit:
            raise AutofixError(
                "target_head_changed", "The Analytics HEAD changed after Autofix approval."
            )
        branch_head = _git(["rev-parse", str(state["branch"])], cwd=repository).lower()
        parent = _git(["rev-parse", f"{repair_commit}^"], cwd=repository).lower()
        if branch_head != repair_commit or parent != base_commit:
            raise AutofixError(
                "commit_mismatch", "The Autofix branch no longer matches the approved commit."
            )
        changed = _git(["diff", "--name-only", base_commit, repair_commit, "--"], cwd=repository)
        validate_changed_paths(changed.splitlines())
        _git(["merge", "--ff-only", repair_commit], cwd=repository)
        try:
            verification = list(validator(repository, base_commit))
        except Exception as error:
            failure = (
                error
                if isinstance(error, AutofixError)
                else AutofixError(
                    "post_merge_validation_failed",
                    "Post-merge deterministic validation failed.",
                )
            )
            state["status"] = "auto_merged_validation_failed"
            state["merged_at"] = _timestamp(current)
            state["failure_category"] = failure.category
            _save_state(state, event="auto_merged_validation_failed")
            _append_report_event(
                state,
                status="auto_merged_validation_failed",
                summary=(
                    f"Approved commit {repair_commit[:12]} was fast-forwarded, but post-merge "
                    "validation failed. Automatic restart and push remain prohibited."
                ),
                verification=failure.category,
                notification_kind="autofix_failed",
            )
            return _public_state(state)
        state["status"] = "auto_merged_pending_deploy"
        state["merged_at"] = _timestamp(current)
        state["merge_verification"] = verification
        state.pop("failure_category", None)
        _save_state(state, event="auto_merged_pending_deploy")
        _append_report_event(
            state,
            status="auto_merged_pending_deploy",
            summary=f"Approved Autofix commit {repair_commit[:12]} was fast-forwarded locally.",
            verification="Post-merge deterministic checks passed; restart, visual review, and push remain manual.",
            notification_kind="autofix_merged",
        )
        return _public_state(state)
    except AutofixError as error:
        _record_failure(state, error, merge=True)
        return _public_state(state)


@contextmanager
def _worker_lock() -> Iterator[None]:
    AUTOFIX_ROOT.mkdir(parents=True, exist_ok=True)
    if AUTOFIX_LOCK_PATH.exists():
        age = time.time() - AUTOFIX_LOCK_PATH.stat().st_mtime
        if age <= RUN_LIFETIME.total_seconds() + 300:
            raise AutofixError("worker_busy", "Another Autofix worker lease is active.")
        AUTOFIX_LOCK_PATH.unlink(missing_ok=True)
    try:
        descriptor = os.open(AUTOFIX_LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as error:
        raise AutofixError("worker_busy", "Another Autofix worker lease is active.") from error
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(json.dumps({"started_at": _timestamp(), "worker": getpass.getuser()}) + "\n")
    try:
        yield
    finally:
        AUTOFIX_LOCK_PATH.unlink(missing_ok=True)


def _pending_states() -> list[dict[str, object]]:
    try:
        paths = sorted(AUTOFIX_STATE_DIR.glob("*.json"), key=lambda path: path.stat().st_mtime)
    except OSError:
        return []
    states = [_load_json(path) for path in paths]
    return [
        state
        for state in states
        if state.get("status") in {"autofix_approved", "autofix_merge_approved"}
    ]


def run_worker_once(*, dry_run: bool = False) -> dict[str, object]:
    """Process at most one approval or report what would run."""

    config = load_config()
    candidates = _pending_states()
    if not candidates:
        return {"status": "idle", "processed": False}
    state = next(
        (item for item in candidates if item.get("status") == "autofix_merge_approved"),
        candidates[0],
    )
    if dry_run or not config["enabled"] or config["mode"] != "active":
        return {
            "status": "dry_run" if dry_run or config["mode"] == "dry_run" else "disabled",
            "processed": False,
            "request_id": state.get("request_id", ""),
            "would_process": state.get("status", "unknown"),
        }
    try:
        with _worker_lock():
            latest = _load_json(_state_path(str(state["request_id"])))
            if latest.get("status") == "autofix_merge_approved":
                result = execute_merge(latest)
            else:
                result = execute_repair(latest)
    except AutofixError as error:
        return {"status": "blocked", "processed": False, "failure_category": error.category}
    return {
        "status": result.get("status", "unknown"),
        "processed": True,
        "request_id": result.get("request_id", ""),
    }
