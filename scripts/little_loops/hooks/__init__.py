"""Hook-intent abstraction layer.

Host-agnostic hook handling for Claude Code, OpenCode, and other agent hosts.

Per-host adapters parse the host's native hook payload into an
:class:`LLHookEvent`, invoke an intent handler under this package
(e.g. ``little_loops.hooks.pre_compact``), and translate the returned
:class:`LLHookResult` back into the host's expected response.

``main_hooks`` is the CLI dispatcher invoked via ``python -m little_loops.hooks
<intent>``. It reads JSON from stdin, builds an :class:`LLHookEvent`, dispatches
to the named intent's ``handle`` function, prints any feedback to stderr, and
exits with the handler's exit code. Today it routes:

- ``pre_compact`` → :mod:`little_loops.hooks.pre_compact`

- ``pre_compact_handoff`` → :mod:`little_loops.hooks.pre_compact_handoff`

- ``session_start`` → :mod:`little_loops.hooks.session_start`

- ``user_prompt_submit`` → :mod:`little_loops.hooks.user_prompt_submit`

- ``post_tool_use`` → :mod:`little_loops.hooks.post_tool_use`

- ``pre_tool_use`` → :mod:`little_loops.hooks.pre_tool_use` (active for Claude Code via hooks.json Write|Edit matcher; opt-in for Codex/OpenCode)

- ``edit_batch_nudge`` → :mod:`little_loops.hooks.edit_batch_nudge` (PostToolUse Edit|Write|MultiEdit matcher; injects an edit-batching reminder)

- ``session_end`` -> :mod:`little_loops.hooks.sweep_stale_refs`

- ``subagent_start`` → :mod:`little_loops.hooks.subagent_start` (records a subagent spawn in ``subagent_runs``)

- ``subagent_stop`` → :mod:`little_loops.hooks.subagent_stop` (closes out the matching ``subagent_runs`` row)

Future intent handlers will be wired by adding entries to the dispatch table
in :func:`main_hooks`.

Every dispatched call is wrapped in :func:`little_loops.session_store.hook_event_context`
(ENH-2506), recording one ``hook_events`` row per fire (exit code, duration,
stderr preview) gated on ``analytics.capture.hooks``. The wrap is best-effort
and never alters the handler's exit code or exception propagation.

Public exports:
    LLHookEvent: host-agnostic hook event payload
    LLHookResult: host-agnostic hook handler response
    main_hooks: CLI entry-point for ``python -m little_loops.hooks``
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from little_loops.hooks.types import LLHookEvent, LLHookResult

__all__ = ["LLHookEvent", "LLHookResult", "main_hooks"]

# Host event name each intent fires under, per hooks/hooks.json (ENH-2506).
# Several intents share a host event (e.g. session_end fires as a secondary
# SessionStart entry, not its own SessionEnd) — this maps the CLI intent
# argument to the event_name recorded in hook_events for aggregate queries.
_INTENT_EVENT_NAME = {
    "pre_compact": "PreCompact",
    "pre_compact_handoff": "PreCompact",
    "session_start": "SessionStart",
    "session_end": "SessionStart",
    "user_prompt_submit": "UserPromptSubmit",
    "post_tool_use": "PostToolUse",
    "pre_tool_use": "PreToolUse",
    "edit_batch_nudge": "PostToolUse",
    "subagent_start": "SubagentStart",
    "subagent_stop": "SubagentStop",
}


def _hooks_telemetry_enabled(cwd: Path) -> bool:
    """True when ``analytics.enabled`` and ``analytics.capture.hooks`` both hold.

    ``analytics.capture.hooks`` defaults to True when absent (forward-compat
    for configs written before ENH-2506), so this reads it via
    :class:`AnalyticsCaptureConfig` rather than a raw dict lookup. Best-effort:
    any config-read failure disables telemetry rather than raising (EPIC-1707
    graceful-degradation contract) — telemetry must never be the reason a
    hook fails.
    """
    try:
        from little_loops.config.core import resolve_config_path
        from little_loops.config.features import AnalyticsCaptureConfig, feature_enabled

        config_path = resolve_config_path(cwd)
        if config_path is None:
            return False
        data = json.loads(config_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return False
        if not feature_enabled(data, "analytics.enabled"):
            return False
        capture = AnalyticsCaptureConfig.from_dict(data.get("analytics", {}).get("capture", {}))
        return capture.hooks
    except Exception:
        return False


_USAGE = (
    "Usage: python -m little_loops.hooks <intent>\n\n"
    "Available intents: pre_compact, pre_compact_handoff, session_start, user_prompt_submit,"
    " post_tool_use, pre_tool_use, edit_batch_nudge, session_end, subagent_start, subagent_stop"
)

_HOOK_INTENT_REGISTRY: dict[str, Callable[[LLHookEvent], LLHookResult]] = {}


def _register_hook_intents(handlers: dict[str, Callable[[LLHookEvent], LLHookResult]]) -> None:
    """Merge extension-provided hook intent handlers into the module registry.

    Raises ValueError on duplicate intent names across extensions.
    """
    for name, handler in handlers.items():
        if name in _HOOK_INTENT_REGISTRY:
            raise ValueError(
                f"Extension conflict: hook intent '{name}' already registered by another extension"
            )
        _HOOK_INTENT_REGISTRY[name] = handler


def _dispatch_table() -> dict[str, Callable[[LLHookEvent], LLHookResult]]:
    # Imported lazily to avoid a top-level circular import surface and keep
    # the module import cost minimal for callers that only need the types.
    from little_loops.hooks import (
        edit_batch_nudge,
        post_tool_use,
        pre_compact,
        pre_compact_handoff,
        pre_tool_use,
        session_start,
        subagent_start,
        subagent_stop,
        sweep_stale_refs,
        user_prompt_submit,
    )

    built_ins: dict[str, Callable[[LLHookEvent], LLHookResult]] = {
        "pre_compact": pre_compact.handle,
        "pre_compact_handoff": pre_compact_handoff.handle,
        "session_start": session_start.handle,
        "session_end": sweep_stale_refs.handle,
        "user_prompt_submit": user_prompt_submit.handle,
        "post_tool_use": post_tool_use.handle,
        "pre_tool_use": pre_tool_use.handle,
        "edit_batch_nudge": edit_batch_nudge.handle,
        "subagent_start": subagent_start.handle,
        "subagent_stop": subagent_stop.handle,
    }
    # Built-ins shadow extension-provided intents on collision.
    return {**_HOOK_INTENT_REGISTRY, **built_ins}


def main_hooks() -> int:
    """CLI entry-point for ``python -m little_loops.hooks <intent>``.

    Reads JSON from stdin, constructs an :class:`LLHookEvent` for the named
    intent, invokes the handler, and translates the :class:`LLHookResult`
    into the Claude Code shell-hook contract (exit code + stderr feedback).
    """
    if len(sys.argv) < 2:
        print(_USAGE, file=sys.stderr)
        return 0

    intent = sys.argv[1]
    handlers = _dispatch_table()
    handler = handlers.get(intent)
    if handler is None:
        print(
            f"Unknown intent: {intent!r}. Available: {', '.join(sorted(handlers))}",
            file=sys.stderr,
        )
        return 1

    raw_stdin = sys.stdin.read() if not sys.stdin.isatty() else ""
    if not raw_stdin.strip():
        return 0
    try:
        parsed = json.loads(raw_stdin)
    except json.JSONDecodeError:
        return 0
    payload: dict[str, Any] = parsed if isinstance(parsed, dict) else {}

    event = LLHookEvent(
        host=os.environ.get("LL_HOOK_HOST", "claude-code"),
        intent=intent,
        payload=payload,
        cwd=os.getcwd(),
        session_id=payload.get("session_id"),
    )
    cwd = Path(event.cwd) if event.cwd else Path.cwd()
    if _hooks_telemetry_enabled(cwd):
        from little_loops.session_store import hook_event_context

        with hook_event_context(
            cwd / ".ll" / "history.db",
            session_id=event.session_id,
            event_name=_INTENT_EVENT_NAME.get(intent, intent),
            matcher=str(payload.get("tool_name")) if payload.get("tool_name") else None,
            script=f"little_loops.hooks.{intent}",
        ) as completion:
            result = handler(event)
            completion.exit_code = result.exit_code
            if result.feedback:
                completion.stderr_preview = result.feedback
    else:
        result = handler(event)
    if result.stdout is not None:
        sys.stdout.write(result.stdout)
    if result.feedback:
        print(result.feedback, file=sys.stderr)
    return result.exit_code
