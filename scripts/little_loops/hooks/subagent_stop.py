"""SubagentStop hook handler: close out a ``subagent_runs`` row (ENH-2505).

Invoked by the dispatcher in ``little_loops.hooks.__init__::main_hooks`` after
a host adapter (e.g. ``hooks/adapters/claude-code/subagent-stop.sh``) parses
the host's stdin payload into an :class:`LLHookEvent`. The payload carries
``agent_id``/``agent_type`` (same values as the matching ``SubagentStart``)
and ``agent_transcript_path`` (the nested transcript path).

Best-effort per the EPIC-1707 contract: never blocks or raises. Budgeted for
sub-second completion — see the known SessionEnd hard-ceiling bug
(``sweep_stale_refs.py``, anthropics/claude-code#32712) this handler must
stay well clear of.
"""

from __future__ import annotations

from pathlib import Path

from little_loops.hooks.types import LLHookEvent, LLHookResult


def handle(event: LLHookEvent) -> LLHookResult:
    """Update the matching ``subagent_runs`` row's ``ended_at``/``status``.

    Always returns ``LLHookResult(exit_code=0)`` — the write is fire-and-forget
    telemetry, never a permission decision.
    """
    try:
        payload = event.payload or {}
        agent_id = payload.get("agent_id")
        agent_type = payload.get("agent_type")
        agent_transcript_path = payload.get("agent_transcript_path")

        from little_loops.session_store import record_subagent_run_stop, resolve_history_db

        record_subagent_run_stop(
            resolve_history_db(Path.cwd() / ".ll" / "history.db"),
            parent_session_id=event.session_id or payload.get("session_id"),
            agent_id=agent_id,
            agent_type=agent_type,
            agent_transcript_path=agent_transcript_path,
            status="completed",
        )
    except Exception:
        pass
    return LLHookResult(exit_code=0)
