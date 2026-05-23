"""PostToolUse hook handler: per-tool byte metrics for context-window analytics.

Persists a row into the ``tool_events`` table of the unified session store
(FEAT-1112) on every tool call. Each row captures ``bytes_in``, ``bytes_out``,
and ``cache_hit`` derived from the ``LLHookEvent`` payload so that downstream
consumers (FEAT-1624 ``/ll:ctx-stats``) can surface which tools consumed the
most context-window bytes during a session.

Guarded by the ``analytics.enabled`` config flag — when absent or false, the
handler is a no-op so projects that do not opt in pay no SQLite cost on the
hot tool-call path. SQLite failures (locked store, missing path, schema drift)
degrade silently: the ``__init__.main_hooks`` dispatcher has no try/except, so
any exception here would surface to the host as a hook failure.
"""

from __future__ import annotations

import contextlib
import json
from pathlib import Path
from typing import Any

from little_loops.config.core import resolve_config_path
from little_loops.config.features import feature_enabled
from little_loops.hooks.types import LLHookEvent, LLHookResult


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


def handle(event: LLHookEvent) -> LLHookResult:
    """Persist per-tool byte metrics to ``tool_events`` (FEAT-1623).

    Gated on ``analytics.enabled``; silent on any failure.
    """
    cwd = Path(event.cwd) if event.cwd else Path.cwd()
    config = _load_config(cwd)
    if config is None or not feature_enabled(config, "analytics.enabled"):
        return LLHookResult(exit_code=0)

    payload = event.payload or {}
    tool_input = payload.get("tool_input", {}) or {}
    tool_response = payload.get("tool_response", {}) or {}
    bytes_in = len(json.dumps(tool_input, default=str))
    bytes_out = len(json.dumps(tool_response, default=str))
    cache_hit = 1 if payload.get("cache_hit") else 0
    tool_name = str(payload.get("tool_name", ""))
    session_id = payload.get("session_id")

    with contextlib.suppress(Exception):
        from little_loops.session_store import _hash_args, _now, connect

        conn = connect(cwd / ".ll" / "session.db")
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

    return LLHookResult(exit_code=0)
