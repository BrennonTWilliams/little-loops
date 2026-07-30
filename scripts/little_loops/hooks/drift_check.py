"""``drift_check`` hook handler: session-start doc-drift surfacing (ENH-2888).

Fires alongside ``session_start`` (see the host adapter wiring below) and
surfaces ``mention``/``route``-severity findings (ENH-2886) from
``doc_counts.verify_documentation()`` — the only walk-light drift source in
the ``doctor.py``/``doc_counts.py``/``link_checker.py`` chain. ``link_checker``
findings are explicitly out of scope: it performs a recursive ``rglob`` and
live HTTP HEAD requests, which would violate this hook's performance contract
(no directory walk, no git call, no cross-workspace sweep).

Findings are throttled to at most once per ``hooks.doc_drift_throttle_days``
(default 7) per project via a timestamp state file
(``.ll/ll-doc-drift-state.json``), modeled on ``edit_batch_nudge.py``'s
throttle/state-file/atomic-write shape. The state path is resolved at call
time (ENH-2927) via ``CLAUDE_PROJECT_DIR`` when the host sets it, else
upward resolution from the event's cwd through
:func:`~little_loops.paths.resolve_ll_dir`; when neither locates a project
this hook silently no-ops. Setting ``LL_DOC_DRIFT_DISABLE``
(any non-empty value) opts out entirely — tests set this to suppress the
check deterministically.

Like every other hook, this handler never blocks: it exits 0 on malformed
input, on internal error, and when findings are reported (feedback is
stderr-only, matching ``sweep_stale_refs.py``'s advisory contract).
"""

from __future__ import annotations

import contextlib
import json
import os
import time
from pathlib import Path
from typing import Any

from little_loops.config.core import resolve_config_path
from little_loops.file_utils import acquire_lock, atomic_write_json
from little_loops.hooks.types import LLHookEvent, LLHookResult
from little_loops.paths import resolve_ll_dir

_DEFAULT_THROTTLE_DAYS = 7
_SECONDS_PER_DAY = 86400

_STATE_FILENAME = "ll-doc-drift-state.json"


def _now() -> float:
    """Wall-clock seconds; wrapped so tests can monkeypatch the clock."""
    return time.time()


def _resolve_state_path(cwd: Path) -> Path | None:
    """Resolve ``.ll/ll-doc-drift-state.json`` without ever creating a stray dir.

    ENH-2927: prefers ``CLAUDE_PROJECT_DIR`` (the host-provided project root)
    when set, else walks upward from *cwd* via
    :func:`~little_loops.paths.resolve_ll_dir`. Returns ``None`` when neither
    locates a project — the caller must treat that as "no-op", never as an
    error.
    """
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    if project_dir:
        try:
            ll_dir = Path(project_dir) / ".ll"
            ll_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            return None
        return ll_dir / _STATE_FILENAME
    resolved_ll_dir = resolve_ll_dir(start=cwd, create=True)
    if resolved_ll_dir is None:
        return None
    return resolved_ll_dir / _STATE_FILENAME


def _load_state(state_path: Path) -> dict[str, Any]:
    """Best-effort read of the throttle state file; empty dict on any error."""
    try:
        data = json.loads(state_path.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError, ValueError):
        return {}


def _persist_state(state_path: Path, state: dict[str, Any]) -> None:
    """Best-effort atomic write under a short advisory lock (never raises)."""
    lock = state_path.with_suffix(state_path.suffix + ".lock")
    try:
        with acquire_lock(lock, timeout=3.0):
            atomic_write_json(state_path, state)
    except TimeoutError:
        with contextlib.suppress(OSError, ValueError):
            atomic_write_json(state_path, state)  # best-effort fallback
    except (OSError, ValueError):
        pass


def _throttle_days(cwd: Path) -> int:
    """Read ``hooks.doc_drift_throttle_days`` from config; default on any error."""
    try:
        config_path = resolve_config_path(cwd)
        if config_path is None:
            return _DEFAULT_THROTTLE_DAYS
        raw_config = json.loads(config_path.read_text(encoding="utf-8"))
        raw_hooks = raw_config.get("hooks", {})
        if not isinstance(raw_hooks, dict):
            return _DEFAULT_THROTTLE_DAYS
        value = raw_hooks.get("doc_drift_throttle_days", _DEFAULT_THROTTLE_DAYS)
        return int(value)
    except (OSError, json.JSONDecodeError, ValueError, TypeError):
        return _DEFAULT_THROTTLE_DAYS


def handle(event: LLHookEvent) -> LLHookResult:
    """Surface throttled ``mention``/``route`` doc-drift findings at session start.

    Always returns ``LLHookResult(exit_code=0)`` — findings are advisory and
    must never block session start.
    """
    if os.environ.get("LL_DOC_DRIFT_DISABLE"):
        return LLHookResult(exit_code=0)

    try:
        payload = event.payload or {}
        raw_cwd = payload.get("cwd") or (event.cwd or "")
        cwd = Path(raw_cwd) if raw_cwd else Path.cwd()

        state_path = _resolve_state_path(cwd)
        if state_path is None:
            # No resolvable project (and no CLAUDE_PROJECT_DIR): silently
            # no-op rather than creating a stray `.ll/` at cwd (ENH-2927).
            return LLHookResult(exit_code=0)
        root = state_path.parent.parent

        now = _now()
        state = _load_state(state_path)
        last_check = state.get("last_check_ts")
        throttle_seconds = _throttle_days(root) * _SECONDS_PER_DAY
        if isinstance(last_check, (int, float)) and (now - float(last_check)) < throttle_seconds:
            return LLHookResult(exit_code=0)

        from little_loops.doc_counts import verify_documentation

        result = verify_documentation(cwd)
        findings = [m for m in result.mismatches if m.action_severity in ("mention", "route")]

        _persist_state(state_path, {"last_check_ts": now})

        if not findings:
            return LLHookResult(exit_code=0)

        lines = [f"[ll] {len(findings)} doc-drift finding(s) surfaced:"]
        for m in findings:
            owner = f" -> {m.route_owner}" if m.route_owner else ""
            lines.append(f"  {m.file}:{m.line}: [{m.category}] {m.action_severity}{owner}")
        return LLHookResult(exit_code=0, feedback="\n".join(lines))
    except Exception:
        return LLHookResult(exit_code=0)
