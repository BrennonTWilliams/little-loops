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
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from little_loops.config.core import resolve_config_path
from little_loops.config.features import PreCompactRubricConfig
from little_loops.file_utils import acquire_lock, atomic_write_json
from little_loops.hooks.types import LLHookEvent, LLHookResult

_FEEDBACK = (
    "[ll] Task state preserved before context compaction. "
    "Check .ll/ll-precompact-state.json if resuming work."
)
_TRANSCRIPT_TAIL_CHARS = 8000


def _load_rubric_config(cwd: Path) -> PreCompactRubricConfig:
    """Load PreCompactRubricConfig from project config, returning defaults on miss."""
    config_path = resolve_config_path(cwd)
    if config_path is None:
        return PreCompactRubricConfig()
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return PreCompactRubricConfig()
    if not isinstance(data, dict):
        return PreCompactRubricConfig()
    return PreCompactRubricConfig.from_dict(
        data.get("hooks", {}).get("pre_compact", {}).get("rubric", {})
    )


def _find_evidence(text: str, signals: list[str]) -> bool:
    """Return True if any signal pattern matches within text (case-insensitive)."""
    if not signals:
        return False
    parts: list[str] = []
    for s in signals:
        try:
            re.compile(s, re.IGNORECASE)
            parts.append(f"(?:{s})")
        except re.error:
            continue
    if not parts:
        return False
    return bool(re.compile("|".join(parts), re.IGNORECASE).search(text))


def should_compact(trajectory_excerpt: str, rubric: PreCompactRubricConfig) -> tuple[bool, str]:
    """Evaluate the SELFCOMPACT rubric over the recent trajectory.

    Returns ``(compact_now, reason)``. Each condition requires verbatim evidence;
    absence defaults to False. ``not_stuck`` fails when stuck signals ARE found.
    """
    conditions = {
        "closed_unit": _find_evidence(trajectory_excerpt, rubric.signals.closed_unit_signals),
        "reducible": _find_evidence(trajectory_excerpt, rubric.signals.reducible_signals),
        "progress": _find_evidence(trajectory_excerpt, rubric.signals.progress_signals),
        "not_stuck": not _find_evidence(trajectory_excerpt, rubric.signals.stuck_signals),
    }
    passed = all(conditions.values())
    reason = ", ".join(k for k, v in conditions.items() if not v) or "all conditions met"
    return passed, reason


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

        # Rubric gate (ENH-2341): defer state writing when reasoning unit is open.
        rubric_cfg = _load_rubric_config(Path.cwd())
        if rubric_cfg.enabled and transcript_path:
            try:
                raw = Path(transcript_path).read_text(encoding="utf-8", errors="replace")
                excerpt = raw[-_TRANSCRIPT_TAIL_CHARS:]
                compact_now, _reason = should_compact(excerpt, rubric_cfg)
                if not compact_now:
                    return LLHookResult(exit_code=0)
            except OSError:
                pass  # graceful degrade: proceed with state write

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

        _record_compaction(state["compacted_at"], event.session_id)
    except Exception:
        return LLHookResult(exit_code=0)

    return LLHookResult(exit_code=2, feedback=_FEEDBACK)


def _record_compaction(compacted_at: str, session_id: str | None) -> None:
    """Best-effort ``compaction`` lifecycle row — never raises (ENH-2495)."""
    try:
        from little_loops.session_store import record_session_lifecycle_event, resolve_history_db

        record_session_lifecycle_event(
            resolve_history_db(Path.cwd() / ".ll" / "history.db"),
            session_id=session_id,
            event="compaction",
            detail={"source": "host_precompact", "state_preserved": True},
            ts=compacted_at,
        )
    except Exception:
        pass
