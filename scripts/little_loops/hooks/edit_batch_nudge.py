"""PostToolUse hook handler: edit-batching nudge (FEAT-2470, wozcode P1).

After an ``Edit``/``Write``/``MultiEdit`` tool call, *conditionally* inject a
short reminder into the model's context to batch independent edits into a single
turn rather than issuing them one-at-a-time. Fewer round-trips means fewer
re-reads of the conversation prefix, which is where the avoidable token cost
lives.

Unlike the original stateless version (which nagged on *every* edit — spending
tokens on a token-cost hook and firing even during unavoidable sequential
dependent edits), this handler tracks consecutive *unbatched* single edits in a
per-session state file and only nudges once a run reaches
``_NUDGE_THRESHOLD`` (default 3) — and then **at most once per session**. After
the first nudge fires, a sticky ``nudged`` latch suppresses every subsequent
nudge for the lifetime of the ``session_id``; a new session re-arms the hook.
Re-firing in the same session adds tokens without changing behavior: a reminder
the model already ignored once is unlikely to land on a 2nd or 3rd repetition.

**Why a time-gap heuristic.** PostToolUse fires once per tool call with no turn
id, so two edits batched in one assistant turn are indistinguishable from two
edits across turns *except* by the wall-clock gap between hook fires. Batched
edits (parallel ``Edit`` calls, or several ``tool_use`` blocks in one message)
execute sub-second apart; a genuine one-edit-per-turn cadence is separated by
full model-generation time (seconds+). So two edits closer than
``_BATCH_WINDOW_SECONDS`` are treated as batched (run reset, no nudge); edits
farther apart advance the unbatched run. ``MultiEdit`` is inherently batched and
always resets the run.

State lives in ``.ll/ll-edit-batch-state.json`` (resolved against the process
cwd, matching the other hooks) as a single record
``{"session_id", "run", "last_ts", "nudged"}``; a changed ``session_id`` resets
the run *and* clears ``nudged``. All state I/O is best-effort — any failure
degrades to a silent pass-through (``exit_code=0``) so the hook never raises
and never spams.

Returns ``LLHookResult(exit_code=2, feedback=…)`` only when the nudge fires, so
the reminder reaches the model's context (``exit_code=0`` feedback is
stderr-only and never seen by the model — see
``little_loops.hooks.types.LLHookResult``). All other tools, and edits that
don't trip the threshold, pass through unchanged (exit 0).

Claude Code wires this handler via
``hooks/adapters/claude-code/edit-batch-nudge.sh`` for the
``"Edit|Write|MultiEdit"`` PostToolUse matcher in ``hooks/hooks.json``; the
same entry is mirrored to Codex via
``scripts/little_loops/hooks/adapters/codex/hooks.json`` — the matcher is
host-agnostic and carries no model-routing semantics.
"""

from __future__ import annotations

import contextlib
import json
import time
from pathlib import Path
from typing import Any

from little_loops.file_utils import acquire_lock, atomic_write_json
from little_loops.hooks.types import LLHookEvent, LLHookResult

_EDIT_TOOLS = frozenset({"Edit", "Write", "MultiEdit"})

# Edits whose hook fires land closer than this (seconds) are treated as one
# batched turn — parallel edits / multiple tool_use blocks in a single message
# execute sub-second apart, whereas a real round-trip includes model generation.
_BATCH_WINDOW_SECONDS = 3.0
# Nudge once a run of consecutive unbatched single edits reaches this length.
_NUDGE_THRESHOLD = 3

_STATE_PATH = Path(".ll/ll-edit-batch-state.json")

_NUDGE = (
    "Edit-batching reminder: when your next changes are independent and target "
    "files you have already read, issue them together in a single turn (parallel "
    "Edit/Write calls, or MultiEdit for one file) instead of one edit per turn. "
    "Batching cuts round-trips and avoidable token cost. Skip this when a later "
    "edit depends on the result of an earlier one."
)


def _now() -> float:
    """Wall-clock seconds; wrapped so tests can monkeypatch the clock."""
    return time.time()


def _load_state() -> dict[str, Any]:
    """Best-effort read of the counter file; empty dict on any error."""
    try:
        data = json.loads(_STATE_PATH.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError, ValueError):
        return {}


def _persist_state(state: dict[str, Any]) -> None:
    """Best-effort atomic write under a short advisory lock (never raises)."""
    lock = _STATE_PATH.with_suffix(_STATE_PATH.suffix + ".lock")
    try:
        with acquire_lock(lock, timeout=3.0):
            atomic_write_json(_STATE_PATH, state)
    except TimeoutError:
        with contextlib.suppress(OSError, ValueError):
            atomic_write_json(_STATE_PATH, state)  # best-effort fallback
    except (OSError, ValueError):
        pass


def handle(event: LLHookEvent) -> LLHookResult:
    """Nudge edit batching at most once per session, only after a run of unbatched single edits."""
    tool_name = event.payload.get("tool_name", "")
    if tool_name not in _EDIT_TOOLS:
        return LLHookResult(exit_code=0)

    # Any failure in the stateful path degrades to a silent pass-through so the
    # hook never raises and never reverts to spamming on every edit.
    try:
        now = _now()
        session = event.payload.get("session_id") or ""
        state = _load_state()
        same_session = state.get("session_id") == session
        run = int(state.get("run", 0)) if same_session else 0
        last_ts = state.get("last_ts") if same_session else None
        # Once we've nudged in this session, never nudge again — the reminder
        # has already had its chance to land, and re-injecting it just adds
        # tokens without changing behavior.
        if same_session and state.get("nudged"):
            return LLHookResult(exit_code=0)

        nudge = False
        if tool_name == "MultiEdit":
            # Inherently batched — never nag; reset any in-progress run.
            run = 0
        elif last_ts is not None and (now - float(last_ts)) < _BATCH_WINDOW_SECONDS:
            # Fired within the batch window of the previous edit → batched.
            run = 0
        else:
            run += 1
            if run >= _NUDGE_THRESHOLD:
                nudge = True
                run = 0

        _persist_state(
            {
                "session_id": session,
                "run": run,
                "last_ts": now,
                "nudged": nudge or (same_session and bool(state.get("nudged"))),
            }
        )
        return LLHookResult(exit_code=2, feedback=_NUDGE) if nudge else LLHookResult(exit_code=0)
    except Exception:  # pragma: no cover — defense in depth; never raise from a hook
        return LLHookResult(exit_code=0)
