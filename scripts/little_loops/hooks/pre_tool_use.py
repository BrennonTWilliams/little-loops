"""PreToolUse hook handler: no-op baseline for opt-in synchronous observability.

Per FEAT-1489 (and FEAT-1488 research), this handler is registered as the
pre-tool-use intent so future consumers (rate-limit enforcement, permission
checks, tool-argument validation) can extend it. Today it returns a passing
result with no side effects.

**Opt-in only**: unlike ``post_tool_use``, this handler runs *synchronously*
in the host's tool-execution path. The OpenCode adapter benchmark measured
cold-start p95 ≈ 10ms (well below the 200ms target), so the cost when
disabled is bounded — but users must explicitly opt in by editing host
config to dispatch ``tool.execute.before`` (OpenCode) or ``PreToolUse``
(Codex) to this intent. By default, neither adapter dispatches it.

See ``hooks/adapters/opencode/README.md`` and
``hooks/adapters/codex/README.md`` for opt-in instructions.
"""

from __future__ import annotations

from little_loops.hooks.types import LLHookEvent, LLHookResult


def handle(event: LLHookEvent) -> LLHookResult:
    """Return a passing result. No-op baseline for future opt-in consumers."""
    del event
    return LLHookResult(exit_code=0)
