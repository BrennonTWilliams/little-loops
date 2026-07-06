"""PostToolUse hook handler: edit-batching nudge (FEAT-2470, wozcode P1).

After an ``Edit``/``Write``/``MultiEdit`` tool call, inject a short reminder
into the model's context to batch independent edits into a single turn rather
than issuing them one-at-a-time. Fewer round-trips means fewer re-reads of the
conversation prefix, which is where the avoidable token cost lives.

Returns ``LLHookResult(exit_code=2, feedback=…)`` for the three edit tools so
the nudge reaches the model's context (``exit_code=0`` feedback is stderr-only
and never seen by the model — see ``little_loops.hooks.types.LLHookResult``).
This mirrors the established non-blocking, context-injected nudge pattern used
by ``pre_compact_handoff.py`` and ``pre_compact.py``. All other tools pass
through unchanged (exit 0).

Claude Code wires this handler via
``hooks/adapters/claude-code/edit-batch-nudge.sh`` for the
``"Edit|Write|MultiEdit"`` PostToolUse matcher in ``hooks/hooks.json``; the
same entry is mirrored to Codex via
``scripts/little_loops/hooks/adapters/codex/hooks.json`` — the matcher is
host-agnostic and carries no model-routing semantics.
"""

from __future__ import annotations

from little_loops.hooks.types import LLHookEvent, LLHookResult

_EDIT_TOOLS = frozenset({"Edit", "Write", "MultiEdit"})

_NUDGE = (
    "Edit-batching reminder: when your next changes are independent and target "
    "files you have already read, issue them together in a single turn (parallel "
    "Edit/Write calls, or MultiEdit for one file) instead of one edit per turn. "
    "Batching cuts round-trips and avoidable token cost. Skip this when a later "
    "edit depends on the result of an earlier one."
)


def handle(event: LLHookEvent) -> LLHookResult:
    """Nudge edit batching after an Edit/Write/MultiEdit; pass-through otherwise."""
    tool_name = event.payload.get("tool_name", "")
    if tool_name in _EDIT_TOOLS:
        return LLHookResult(exit_code=2, feedback=_NUDGE)
    return LLHookResult(exit_code=0)
