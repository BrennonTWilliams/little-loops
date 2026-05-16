"""PostToolUse hook handler: no-op baseline for fire-and-forget observability.

Per FEAT-1489, this handler is wired as the post-tool-use intent on Codex and
OpenCode so future consumers (audit logging, token budgeting, rate-limit
enforcement) have a stable registration point. Today it returns a passing
result with no side effects — the no-op baseline matches ``session_start``'s
``exit_code=0`` convention rather than ``pre_compact``'s ``exit_code=2``
block-and-inject pattern.

Fire-and-forget semantics are achieved through handler speed (<200ms p95
no-op) on the Codex blocking-shim adapter (≤5s timeout) and through the
no-await invocation pattern on the OpenCode adapter. The handler itself
does not background or spawn anything.
"""

from __future__ import annotations

from little_loops.hooks.types import LLHookEvent, LLHookResult


def handle(event: LLHookEvent) -> LLHookResult:
    """Return a passing result. No-op baseline for future consumers."""
    del event
    return LLHookResult(exit_code=0)
