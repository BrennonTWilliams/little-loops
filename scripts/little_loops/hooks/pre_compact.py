"""PreCompact hook handler: preserve task state before context compaction.

Python port of ``hooks/scripts/precompact-state.sh`` (FEAT-1449). The
``handle`` function is invoked by the dispatcher in
``little_loops.hooks.__init__::main_hooks`` after the Claude Code adapter
(``hooks/adapters/claude-code/precompact.sh``) parses the host's stdin
payload into an :class:`LLHookEvent`.

The wire-visible output is ``.ll/ll-precompact-state.json``; its shape is
read by ``hooks/scripts/context-monitor.sh::check_compaction`` (only the
``compacted_at`` key) and by resume-prompt logic (the optional keys).
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from little_loops.file_utils import acquire_lock, atomic_write_json
from little_loops.hooks.types import LLHookEvent, LLHookResult

_FEEDBACK = (
    "[ll] Task state preserved before context compaction. "
    "Check .ll/ll-precompact-state.json if resuming work."
)


def handle(event: LLHookEvent) -> LLHookResult:
    """Preserve task state before context compaction.

    Writes ``.ll/ll-precompact-state.json`` atomically (with a 3s advisory
    lock + best-effort fallback) so post-compact resume logic can find:

    - ``compacted_at`` — UTC ISO 8601 timestamp (consumed by
      ``context-monitor.sh::check_compaction``)
    - ``transcript_path`` — from the host payload, or ``""``
    - ``preserved: true``
    - ``context_state_at_compact`` — merged from ``.ll/ll-context-state.json``
      when that file exists
    - ``recent_plan_files`` — up to 5 paths under ``thoughts/shared/plans/``
      modified in the last 24h (filesystem-iteration order, matching the
      shell ``find ... | head -5`` semantics)
    - ``continue_prompt_exists: true`` — key present **only** when
      ``.ll/ll-continue-prompt.md`` exists (key omitted otherwise, matching
      the shell ``jq '. + {continue_prompt_exists: true}'`` branch)

    Returns ``LLHookResult(exit_code=2, ...)`` so Claude Code surfaces the
    feedback string to the user via stderr.
    """
    try:
        payload = event.payload or {}
        transcript_path = payload.get("transcript_path") or ""

        state_dir = Path(".ll")
        state_file = state_dir / "ll-precompact-state.json"
        state_lock = state_dir / "ll-precompact-state.json.lock"
        context_state_file = state_dir / "ll-context-state.json"
        plans_dir = Path("thoughts/shared/plans")
        continue_prompt = state_dir / "ll-continue-prompt.md"

        state: dict[str, Any] = {
            "compacted_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "transcript_path": transcript_path,
            "preserved": True,
        }

        if context_state_file.is_file():
            try:
                state["context_state_at_compact"] = json.loads(
                    context_state_file.read_text(encoding="utf-8")
                )
            except (OSError, json.JSONDecodeError):
                pass

        if plans_dir.is_dir():
            cutoff = time.time() - 86400
            recent: list[str] = []
            for p in plans_dir.glob("*.md"):
                try:
                    if p.stat().st_mtime > cutoff:
                        recent.append(str(p))
                except OSError:
                    continue
                if len(recent) >= 5:
                    break
            state["recent_plan_files"] = recent
        else:
            state["recent_plan_files"] = []

        if continue_prompt.exists():
            state["continue_prompt_exists"] = True

        try:
            with acquire_lock(state_lock, timeout=3.0):
                atomic_write_json(state_file, state)
        except TimeoutError:
            atomic_write_json(state_file, state)
    except Exception:
        return LLHookResult(exit_code=0)

    return LLHookResult(exit_code=2, feedback=_FEEDBACK)
