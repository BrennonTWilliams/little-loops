"""PostToolUse hook handler: per-tool byte metrics and file-event recording.

Persists a row into the ``tool_events`` table of the unified session store
(FEAT-1112) on every tool call, and a row into ``file_events`` for tool calls
that touch a file (ENH-1832). ``tool_events`` rows capture ``bytes_in``,
``bytes_out``, and ``cache_hit``; ``file_events`` rows capture the file path,
op (tool name), and optional issue ID extracted from the path.

Guarded by the ``analytics.enabled`` config flag — when absent or false, the
handler is a no-op so projects that do not opt in pay no SQLite cost on the
hot tool-call path. SQLite failures (locked store, missing path, schema drift)
degrade silently: the ``__init__.main_hooks`` dispatcher has no try/except, so
any exception here would surface to the host as a hook failure.
"""

from __future__ import annotations

import contextlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from little_loops.config.core import resolve_config_path
from little_loops.config.features import AnalyticsCaptureConfig, feature_enabled
from little_loops.hooks.types import LLHookEvent, LLHookResult

# Matches a file-path token inside a Bash command string.  Two alternatives:
#   1. Paths that start with ./, ../, or / (absolute/explicit-relative)
#   2. Paths that start with a letter and contain at least one / (e.g. scripts/foo.py)
# Anchored by start-of-string or preceding whitespace so flag-like tokens
# (e.g. -v, --flag) are not mistaken for paths.
_BASH_PATH_RE = re.compile(r"(?:^|\s)((?:\./|\.\.\/|/)[^\s\"'|&;><]+|[A-Za-z][\w./\-]*/[\w./\-]+)")

# Matches an issue ID (e.g. ENH-1832, BUG-007) within a file path.
_ISSUE_ID_RE = re.compile(r"((?:BUG|FEAT|ENH|EPIC)-\d+)")


def _load_config(cwd: Path) -> dict[str, Any] | None:
    """Load ``.ll/ll-config.json`` (host-aware), returning None on miss/error."""
    config_path = resolve_config_path(cwd)
    if config_path is None:
        return None
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _extract_file_path(tool_name: str, tool_input: dict[str, Any]) -> str | None:
    """Return the primary file path from a tool_input dict, or None if not applicable."""
    if tool_name in {"Read", "Write", "Edit"}:
        return tool_input.get("file_path") or None
    if tool_name == "Glob":
        return tool_input.get("path") or tool_input.get("pattern") or None
    if tool_name == "Grep":
        return tool_input.get("path") or None
    if tool_name == "Bash":
        cmd = tool_input.get("command") or ""
        m = _BASH_PATH_RE.search(cmd)
        return m.group(1) if m else None
    return None


def _normalize_path(raw: str, cwd: Path) -> str:
    """Return path relative to cwd with no leading './'.

    Relative paths are returned as-is (preserving trailing slash / glob patterns)
    after stripping a leading './'.  Absolute paths are made relative to cwd when
    possible, falling back to the original string.
    """
    p = Path(raw)
    if p.is_absolute():
        try:
            return str(p.relative_to(cwd))
        except ValueError:
            return raw
    return raw[2:] if raw.startswith("./") else raw


def _detect_issue_id(path: str) -> str | None:
    """Return an issue ID if the path points into .issues/, else None."""
    if ".issues/" not in path:
        return None
    m = _ISSUE_ID_RE.search(path)
    return m.group(1) if m else None


def _maybe_auto_commit(config: dict[str, Any], cwd: Path, file_path: str, tool_name: str) -> None:
    """Auto-commit an issue file change when issues.auto_commit is enabled (ENH-1844)."""
    if not feature_enabled(config, "issues.auto_commit"):
        return

    filename = Path(file_path).name
    if not re.match(r"^P[0-5]-(BUG|FEAT|ENH|EPIC)-\d{3,}", filename):
        return

    issues_cfg = config.get("issues", {})
    base_dir: str = issues_cfg.get("base_dir", ".issues")
    norm = file_path.replace("\\", "/")
    if f"/{base_dir}/" not in norm and not norm.startswith(f"{base_dir}/"):
        return

    prefix: str = issues_cfg.get("auto_commit_prefix", "chore(issues)")
    m = re.match(r"^P[0-5]-((BUG|FEAT|ENH|EPIC)-\d+)-(.+?)\.md$", filename)
    if not m:
        return
    issue_id = m.group(1)
    slug = m.group(3)
    verb = "capture" if tool_name == "Write" else "update"
    commit_msg = f"{prefix}: {verb} {issue_id} {slug}"

    abs_path = Path(file_path) if Path(file_path).is_absolute() else (cwd / file_path)

    with contextlib.suppress(Exception):
        subprocess.run(["git", "add", str(abs_path)], cwd=str(cwd), check=True, capture_output=True)
        status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=True,
        )
        other_changes = [ln for ln in status_result.stdout.splitlines() if filename not in ln]
        if other_changes:
            return
        subprocess.run(
            ["git", "commit", "-m", commit_msg],
            cwd=str(cwd),
            check=True,
            capture_output=True,
        )


def handle(event: LLHookEvent) -> LLHookResult:
    """Persist per-tool byte metrics and auto-commit issue files when configured.

    Analytics writes are gated on ``analytics.enabled``; auto-commit is gated on
    ``issues.auto_commit``. Both features degrade silently on failure.
    """
    cwd = Path(event.cwd) if event.cwd else Path.cwd()
    config = _load_config(cwd)

    payload = event.payload or {}
    tool_input = payload.get("tool_input", {}) or {}
    tool_name = str(payload.get("tool_name", ""))
    raw_path = _extract_file_path(tool_name, tool_input)

    if config is not None and feature_enabled(config, "analytics.enabled"):
        tool_response = payload.get("tool_response", {}) or {}
        bytes_in = len(json.dumps(tool_input, default=str))
        bytes_out = len(json.dumps(tool_response, default=str))
        cache_hit = 1 if payload.get("cache_hit") else 0
        session_id = payload.get("session_id")

        with contextlib.suppress(Exception):
            from little_loops.session_store import _hash_args, _now, connect

            conn = connect(cwd / ".ll" / "history.db")
            try:
                conn.execute(
                    "INSERT INTO tool_events(ts, session_id, tool_name, args_hash, "
                    "result_size, bytes_in, bytes_out, cache_hit) "
                    "VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        _now(),
                        session_id,
                        tool_name,
                        _hash_args(tool_input),
                        bytes_out,
                        bytes_in,
                        bytes_out,
                        cache_hit,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

        if raw_path:
            capture = AnalyticsCaptureConfig.from_dict(
                config.get("analytics", {}).get("capture", {})
            )
            if capture.file_events:
                with contextlib.suppress(Exception):
                    from little_loops.session_store import write_file_event

                    norm_path = _normalize_path(raw_path, cwd)
                    issue_id = _detect_issue_id(norm_path)
                    write_file_event(
                        cwd / ".ll" / "history.db",
                        session_id,
                        norm_path,
                        tool_name,
                        issue_id,
                    )
            # TODO(ENH-1835): wire analytics.capture.skills gate when ENH-1833 lands

    if config is not None and tool_name in {"Write", "Edit"} and raw_path:
        _maybe_auto_commit(config, cwd, raw_path, tool_name)

    if tool_name == "Bash":
        from little_loops.hooks import install_learning_gate

        return install_learning_gate.gate(event)

    return LLHookResult(exit_code=0)
