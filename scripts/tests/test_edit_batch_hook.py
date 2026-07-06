"""Python-direct tests for ``little_loops.hooks.edit_batch_nudge.handle`` (FEAT-2470).

The handler nudges edit-batching after an Edit/Write/MultiEdit tool call by
returning ``LLHookResult(exit_code=2, feedback=…)`` so the reminder reaches the
model's context; every other tool passes through with exit 0 and no feedback.
Follows the ``TestPostToolUseBaseline`` layout in ``test_hook_post_tool_use.py``
(synthetic ``LLHookEvent`` factory, direct handler call).
"""

from __future__ import annotations

from little_loops.hooks.edit_batch_nudge import handle
from little_loops.hooks.types import LLHookEvent


def _event(payload: dict | None = None, *, cwd: str | None = None) -> LLHookEvent:
    return LLHookEvent(
        host="claude-code",
        intent="edit_batch_nudge",
        payload=payload or {},
        cwd=cwd,
    )


class TestEditBatchNudge:
    def test_edit_tool_injects_nudge(self) -> None:
        result = handle(_event({"tool_name": "Edit"}))
        assert result.exit_code == 2
        assert result.feedback is not None
        assert "batch" in result.feedback.lower()

    def test_write_tool_injects_nudge(self) -> None:
        result = handle(_event({"tool_name": "Write"}))
        assert result.exit_code == 2
        assert result.feedback

    def test_multiedit_tool_injects_nudge(self) -> None:
        result = handle(_event({"tool_name": "MultiEdit"}))
        assert result.exit_code == 2
        assert result.feedback

    def test_non_edit_tool_passes_through(self) -> None:
        result = handle(_event({"tool_name": "Bash", "tool_input": {"command": "ls"}}))
        assert result.exit_code == 0
        assert result.feedback is None

    def test_empty_payload_passes_through(self) -> None:
        # Missing tool_name must not raise and must not nudge.
        result = handle(_event())
        assert result.exit_code == 0
        assert result.feedback is None

    def test_read_tool_passes_through(self) -> None:
        result = handle(_event({"tool_name": "Read"}))
        assert result.exit_code == 0
        assert result.feedback is None

    def test_handler_does_not_mutate_payload(self) -> None:
        payload = {"tool_name": "Edit"}
        handle(_event(payload))
        assert payload == {"tool_name": "Edit"}
