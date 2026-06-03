"""PreToolUse hook handler: learning-test discoverability gate (FEAT-1742).

Dispatches Write/Edit tool calls to the learning_tests_gate for import
detection and registry probing. All other tool calls pass through unchanged.

The gate is a no-op when ``learning_tests.enabled`` is false (default) or
``learning_tests.discoverability.mode`` is ``"off"``. When enabled, it
emits a soft nudge (warn mode, exit 0) or blocks (block mode, exit 2) when
a file being written imports packages with no proven Learning Test record.

Claude Code wires this handler via
``hooks/adapters/claude-code/pre-tool-use.sh`` for the ``"Write|Edit"``
matcher in ``hooks/hooks.json``. Codex and OpenCode users opt in separately
— see ``hooks/adapters/codex/README.md`` and
``hooks/adapters/opencode/README.md``.
"""

from __future__ import annotations

from little_loops.hooks.types import LLHookEvent, LLHookResult


def handle(event: LLHookEvent) -> LLHookResult:
    """Dispatch Write/Edit to discoverability gate; pass-through for other tools."""
    tool_name = event.payload.get("tool_name", "")
    if tool_name in {"Write", "Edit"}:
        from little_loops.hooks.learning_tests_gate import gate

        return gate(event)
    return LLHookResult(exit_code=0)
