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

- ``session_start`` → :mod:`little_loops.hooks.session_start`

Future intent handlers will be wired by adding entries to the dispatch table
in :func:`main_hooks`.

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
from typing import Any

from little_loops.hooks.types import LLHookEvent, LLHookResult

__all__ = ["LLHookEvent", "LLHookResult", "main_hooks"]

_USAGE = (
    "Usage: python -m little_loops.hooks <intent>\n\nAvailable intents: pre_compact, session_start"
)


def _dispatch_table() -> dict[str, Callable[[LLHookEvent], LLHookResult]]:
    # Imported lazily to avoid a top-level circular import surface and keep
    # the module import cost minimal for callers that only need the types.
    from little_loops.hooks import pre_compact, session_start

    return {
        "pre_compact": pre_compact.handle,
        "session_start": session_start.handle,
    }


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
    )
    result = handler(event)
    if result.stdout is not None:
        sys.stdout.write(result.stdout)
    if result.feedback:
        print(result.feedback, file=sys.stderr)
    return result.exit_code
