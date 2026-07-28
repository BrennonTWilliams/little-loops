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
throttle/state-file/atomic-write shape. Setting ``LL_DOC_DRIFT_DISABLE``
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

_DEFAULT_THROTTLE_DAYS = 7
_SECONDS_PER_DAY = 86400

_STATE_FILENAME = "ll-doc-drift-state.json"


def _now() -> float:
    """Wall-clock seconds; wrapped so tests can monkeypatch the clock."""
    return time.time()


def _state_path(cwd: Path) -> Path:
    return cwd / ".ll" / _STATE_FILENAME


def _load_state(cwd: Path) -> dict[str, Any]:
    """Best-effort read of the throttle state file; empty dict on any error."""
    try:
        data = json.loads(_state_path(cwd).read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError, ValueError):
        return {}


def _persist_state(cwd: Path, state: dict[str, Any]) -> None:
    """Best-effort atomic write under a short advisory lock (never raises)."""
    path = _state_path(cwd)
    lock = path.with_suffix(path.suffix + ".lock")
    try:
        with acquire_lock(lock, timeout=3.0):
            atomic_write_json(path, state)
    except TimeoutError:
        with contextlib.suppress(OSError, ValueError):
            atomic_write_json(path, state)  # best-effort fallback
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

        now = _now()
        state = _load_state(cwd)
        last_check = state.get("last_check_ts")
        throttle_seconds = _throttle_days(cwd) * _SECONDS_PER_DAY
        if isinstance(last_check, (int, float)) and (now - float(last_check)) < throttle_seconds:
            return LLHookResult(exit_code=0)

        from little_loops.doc_counts import verify_documentation

        result = verify_documentation(cwd)
        findings = [m for m in result.mismatches if m.action_severity in ("mention", "route")]

        _persist_state(cwd, {"last_check_ts": now})

        if not findings:
            return LLHookResult(exit_code=0)

        lines = [f"[ll] {len(findings)} doc-drift finding(s) surfaced:"]
        for m in findings:
            owner = f" -> {m.route_owner}" if m.route_owner else ""
            lines.append(f"  {m.file}:{m.line}: [{m.category}] {m.action_severity}{owner}")
        return LLHookResult(exit_code=0, feedback="\n".join(lines))
    except Exception:
        return LLHookResult(exit_code=0)
