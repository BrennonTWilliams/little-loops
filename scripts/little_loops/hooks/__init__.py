"""Hook-intent abstraction layer.

Host-agnostic hook handling for Claude Code, OpenCode, and other agent hosts.

Per-host adapters parse the host's native hook payload into an
:class:`LLHookEvent`, invoke an intent handler under this package
(e.g. ``little_loops.hooks.pre_compact``), and translate the returned
:class:`LLHookResult` back into the host's expected response.

This module currently exposes the foundational types and a CLI entry-point
stub. Concrete intent handlers (``pre_compact``, ``session_start``, …) land
in follow-up issues (FEAT-1449, FEAT-1450, …).

Public exports:
    LLHookEvent: host-agnostic hook event payload
    LLHookResult: host-agnostic hook handler response
    main_hooks: CLI entry-point for ``python -m little_loops.hooks``
"""

from __future__ import annotations

import sys

from little_loops.hooks.types import LLHookEvent, LLHookResult

__all__ = ["LLHookEvent", "LLHookResult", "main_hooks"]


def main_hooks() -> int:
    """CLI entry-point for ``python -m little_loops.hooks <intent>``.

    Stub for FEAT-1448. Concrete intent dispatch lands in FEAT-1449
    (``pre_compact``) and FEAT-1450 (``session_start``). Today this prints
    usage and exits ``0``.
    """
    print(
        "Usage: python -m little_loops.hooks <intent>\n"
        "\n"
        "No intents are wired yet. The hook-intent dispatch layer is a stub; "
        "concrete handlers (pre_compact, session_start, …) land in follow-up "
        "issues (FEAT-1449, FEAT-1450).",
        file=sys.stderr,
    )
    return 0
