"""Python-direct tests for ``little_loops.hooks.post_tool_use.handle`` (FEAT-1489).

The handler is a no-op baseline returning ``LLHookResult(exit_code=0)`` —
fire-and-forget observability registration point for future consumers on
Codex and OpenCode. Adapter round-trip tests live in
``test_codex_adapter.py``; this module exercises the pure-function handler
under unit conditions.
"""

from __future__ import annotations

from little_loops.hooks.post_tool_use import handle as post_handle
from little_loops.hooks.pre_tool_use import handle as pre_handle
from little_loops.hooks.types import LLHookEvent

# Alias kept for the existing test class below.
handle = post_handle


def _event(payload: dict | None = None) -> LLHookEvent:
    return LLHookEvent(host="codex", intent="post_tool_use", payload=payload or {})


class TestPostToolUseBaseline:
    def test_empty_payload_returns_pass(self) -> None:
        result = handle(_event())
        assert result.exit_code == 0
        assert result.feedback is None
        assert result.stdout is None
        assert result.decision is None
        # ``LLHookResult.data`` defaults to ``{}`` (not ``None``) — the
        # no-op handler doesn't populate it.
        assert not result.data

    def test_arbitrary_payload_returns_pass(self) -> None:
        # The handler must tolerate any payload shape — Codex's PostToolUse and
        # OpenCode's tool.execute.after both pass tool-specific structures that
        # the no-op baseline ignores entirely.
        result = handle(
            _event(
                {
                    "tool_name": "Write",
                    "tool_input": {"file_path": "/tmp/foo", "content": "bar"},
                    "tool_response": {"success": True},
                    "session_id": "sess-1",
                }
            )
        )
        assert result.exit_code == 0
        assert result.feedback is None
        assert result.stdout is None

    def test_handler_does_not_mutate_payload(self) -> None:
        payload = {"tool_name": "Bash"}
        handle(_event(payload))
        assert payload == {"tool_name": "Bash"}

    def test_handler_is_host_agnostic(self) -> None:
        for host in ("claude-code", "codex", "opencode"):
            result = handle(LLHookEvent(host=host, intent="post_tool_use", payload={}))
            assert result.exit_code == 0, f"non-zero exit for host={host}"


class TestPreToolUseBaseline:
    """Pre-tool-use handler is registered for opt-in dispatch (FEAT-1489)."""

    def test_empty_payload_returns_pass(self) -> None:
        result = pre_handle(LLHookEvent(host="codex", intent="pre_tool_use", payload={}))
        assert result.exit_code == 0
        assert result.feedback is None
        assert result.stdout is None

    def test_arbitrary_payload_returns_pass(self) -> None:
        result = pre_handle(
            LLHookEvent(
                host="opencode",
                intent="pre_tool_use",
                payload={"tool_name": "Bash", "tool_input": {"command": "rm -rf /"}},
            )
        )
        assert result.exit_code == 0
