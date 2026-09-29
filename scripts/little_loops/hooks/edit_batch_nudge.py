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
``_NUDGE_THRESHOLD`` (default 3, ``hooks.edit_batch_nudge.threshold``) — and then **at most once per session**. After
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
``_BATCH_WINDOW_SECONDS`` (``hooks.edit_batch_nudge.window_seconds``) are treated as batched (run reset, no nudge); edits
farther apart advance the unbatched run. ``MultiEdit`` is inherently batched and
always resets the run.

State lives in ``.ll/ll-edit-batch-state.json``, resolved at call time
(ENH-2927) via ``CLAUDE_PROJECT_DIR`` (when the host sets it) or else upward
resolution from the event's cwd through
:func:`~little_loops.paths.find_project_root`; when neither locates a project
this hook is a silent no-op (never writes, never errors — see
:func:`_resolve_project_root`). ``hooks.edit_batch_nudge.enabled: false``
(ENH-3645, ``.ll/ll-config.json`` or ``.ll/ll.local.md``) makes it a no-op too. The record shape is
``{"session_id", "run", "last_ts", "nudged"}``; a changed ``session_id`` resets
the run *and* clears ``nudged``. All state I/O is best-effort — any failure
degrades to a silent pass-through (``exit_code=0``) so the hook never raises
and never spams.

When the nudge fires, the reminder reaches the model's context via a
host-conditional channel (ENH-2994): on Claude Code (``event.host ==
"claude-code"``), ``exit_code=0`` with a ``hookSpecificOutput.additionalContext``
JSON payload on stdout — Claude Code renders exit 2 from ``PostToolUse`` as a
blocking-error banner, which is misleading for a purely advisory reminder that
blocks nothing. Other hosts (Codex) translate exit codes rather than reading a
Claude Code-specific stdout schema, so they keep the original
``LLHookResult(exit_code=2, feedback=…)`` channel (``exit_code=0`` feedback is
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
import math
import os
import time
from pathlib import Path
from typing import Any

from little_loops.config.core import (
    deep_merge,
    parse_local_override_frontmatter,
    resolve_config_path,
)
from little_loops.file_utils import acquire_lock, atomic_write_json
from little_loops.hooks.types import LLHookEvent, LLHookResult
from little_loops.paths import find_project_root

_EDIT_TOOLS = frozenset({"Edit", "Write", "MultiEdit"})

# Edits whose hook fires land closer than this (seconds) are treated as one
# batched turn — parallel edits / multiple tool_use blocks in a single message
# execute sub-second apart, whereas a real round-trip includes model generation.
_BATCH_WINDOW_SECONDS = 3.0
# Nudge once a run of consecutive unbatched single edits reaches this length.
_NUDGE_THRESHOLD = 3

_STATE_FILENAME = "ll-edit-batch-state.json"

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


def _resolve_project_root(cwd: Path) -> Path | None:
    """Resolve the project root without creating anything.

    ENH-2927: prefers ``CLAUDE_PROJECT_DIR`` (the host-provided project root)
    when set, else walks upward from *cwd* via
    :func:`~little_loops.paths.find_project_root`. Returns ``None`` when neither
    locates a project. Config and state are both resolved from this one root so
    they cannot drift apart.
    """
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    if project_dir:
        # The host vouches for this being the project root — use it directly
        # rather than re-deriving one via upward resolution.
        return Path(project_dir)
    return find_project_root(cwd)


def _resolve_state_path(root: Path) -> Path | None:
    """Resolve ``.ll/ll-edit-batch-state.json`` under *root*, creating ``.ll/``.

    The only step in this module that may ``mkdir``; callers run it after the
    ``enabled`` gate so a disabled hook never creates a stray ``.ll/`` (ENH-2927).
    Returns ``None`` when the directory cannot be created.
    """
    try:
        ll_dir = root / ".ll"
        ll_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    return ll_dir / _STATE_FILENAME


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _load_settings(root: Path) -> tuple[bool, int, float]:
    """Read ``hooks.edit_batch_nudge`` as ``(enabled, threshold, window_seconds)`` (ENH-3645).

    Merges ``.ll/ll.local.md`` frontmatter over the base config. Never raises;
    a missing/unreadable/malformed source or an invalid value falls back to the
    default for that key only (absent or non-bool ``enabled`` means enabled).
    """
    enabled, threshold, window = True, _NUDGE_THRESHOLD, _BATCH_WINDOW_SECONDS
    try:
        merged: dict[str, Any] = {}
        config_path = resolve_config_path(root)
        if config_path is not None:
            merged = _as_dict(json.loads(config_path.read_text(encoding="utf-8")))
        local_file = root / ".ll" / "ll.local.md"
        if local_file.is_file():
            overrides = parse_local_override_frontmatter(local_file.read_text(encoding="utf-8"))
            if overrides:
                merged = deep_merge(merged, overrides)
        cfg = _as_dict(_as_dict(merged.get("hooks")).get("edit_batch_nudge"))
    except (OSError, ValueError, TypeError, AttributeError):
        return enabled, threshold, window

    if cfg.get("enabled") is False:
        enabled = False

    raw_threshold = cfg.get("threshold")
    if isinstance(raw_threshold, float) and raw_threshold.is_integer():
        raw_threshold = int(raw_threshold)
    if (
        isinstance(raw_threshold, int)
        and not isinstance(raw_threshold, bool)
        and raw_threshold >= 1
    ):
        threshold = raw_threshold

    raw_window = cfg.get("window_seconds")
    if (
        isinstance(raw_window, (int, float))
        and not isinstance(raw_window, bool)
        and math.isfinite(raw_window)
        and raw_window >= 0
    ):
        window = float(raw_window)

    return enabled, threshold, window


def _load_state(state_path: Path) -> dict[str, Any]:
    """Best-effort read of the counter file; empty dict on any error."""
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


def handle(event: LLHookEvent) -> LLHookResult:
    """Nudge edit batching at most once per session, only after a run of unbatched single edits."""
    tool_name = event.payload.get("tool_name", "")
    if tool_name not in _EDIT_TOOLS:
        return LLHookResult(exit_code=0)

    # Any failure in the stateful path degrades to a silent pass-through so the
    # hook never raises and never reverts to spamming on every edit.
    try:
        raw_cwd = event.payload.get("cwd") or event.cwd or ""
        cwd = Path(raw_cwd) if raw_cwd else Path.cwd()
        root = _resolve_project_root(cwd)
        if root is None:
            # No resolvable project (and no CLAUDE_PROJECT_DIR): silently
            # no-op rather than creating a stray `.ll/` at cwd (ENH-2927).
            return LLHookResult(exit_code=0)
        enabled, threshold, window = _load_settings(root)
        if not enabled:
            return LLHookResult(exit_code=0)
        state_path = _resolve_state_path(root)
        if state_path is None:
            return LLHookResult(exit_code=0)

        now = _now()
        session = event.payload.get("session_id") or ""
        state = _load_state(state_path)
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
        elif last_ts is not None and (now - float(last_ts)) < window:
            # Fired within the batch window of the previous edit → batched.
            run = 0
        else:
            run += 1
            if run >= threshold:
                nudge = True
                run = 0

        _persist_state(
            state_path,
            {
                "session_id": session,
                "run": run,
                "last_ts": now,
                "nudged": nudge or (same_session and bool(state.get("nudged"))),
            },
        )
        if not nudge:
            return LLHookResult(exit_code=0)
        if event.host == "claude-code":
            return LLHookResult(
                exit_code=0,
                # Retained for hook_events.stderr_preview telemetry only; exit-0
                # stderr is verbose-mode only and never reaches the model, so this
                # does not double-inject the nudge.
                feedback=_NUDGE,
                stdout=json.dumps(
                    {
                        "hookSpecificOutput": {
                            "hookEventName": "PostToolUse",
                            "additionalContext": _NUDGE,
                        }
                    }
                ),
            )
        # Other hosts translate exit codes; exit 2 stays their model-visible channel.
        return LLHookResult(exit_code=2, feedback=_NUDGE)
    except Exception:  # pragma: no cover — defense in depth; never raise from a hook
        return LLHookResult(exit_code=0)
