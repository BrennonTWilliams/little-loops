"""SubagentStart hook handler: record a subagent spawn in ``subagent_runs`` (ENH-2505).

Invoked by the dispatcher in ``little_loops.hooks.__init__::main_hooks`` after
a host adapter (e.g. ``hooks/adapters/claude-code/subagent-start.sh``) parses
the host's stdin payload into an :class:`LLHookEvent`. The payload carries
``agent_id`` (spawn-local identifier, scoped to the parent session — not a
``sessions.session_id``) and ``agent_type`` (the subagent label, e.g.
``"Explore"``, ``"codebase-locator"``).

Best-effort per the EPIC-1707 contract: never blocks or raises. A missing
``agent_id`` is a silent no-op, never a hard failure.
"""

from __future__ import annotations

from pathlib import Path

from little_loops.hooks.types import LLHookEvent, LLHookResult


def handle(event: LLHookEvent) -> LLHookResult:
    """Write a ``running`` row to ``subagent_runs`` for this spawn.

    Always returns ``LLHookResult(exit_code=0)`` — the write is fire-and-forget
    telemetry, never a permission decision.
    """
    try:
        payload = event.payload or {}
        agent_id = payload.get("agent_id")
        agent_type = payload.get("agent_type")

        from little_loops.session_store import record_subagent_run_start, resolve_history_db

        record_subagent_run_start(
            resolve_history_db(Path.cwd() / ".ll" / "history.db"),
            parent_session_id=event.session_id or payload.get("session_id"),
            agent_id=agent_id,
            agent_type=agent_type,
        )
    except Exception:
        pass
    return LLHookResult(exit_code=0)
