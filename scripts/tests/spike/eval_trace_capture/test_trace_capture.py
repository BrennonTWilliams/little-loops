"""AC tests for the FEAT-2878 trace-capture spike. See spike-FEAT-2878.md."""

from __future__ import annotations

import ast
import json
from pathlib import Path

from tests.spike.eval_trace_capture.trace_capture import ToolCall, extract_tool_calls


def _assistant_event(blocks: list[dict]) -> str:
    return json.dumps({"type": "assistant", "message": {"content": blocks}})


def _text_block(text: str) -> dict:
    return {"type": "text", "text": text}


def _tool_use_block(name: str, tool_input: dict) -> dict:
    return {"type": "tool_use", "name": name, "input": tool_input}


class TestTraceCapture:
    def test_ordered_trace_across_multiple_assistant_events(self):
        lines = [
            _assistant_event([_tool_use_block("Read", {"path": "a.py"})]),
            _assistant_event([_tool_use_block("Edit", {"path": "a.py"})]),
            _assistant_event([_tool_use_block("Bash", {"command": "pytest"})]),
        ]

        calls = extract_tool_calls(lines)

        assert [c.name for c in calls] == ["Read", "Edit", "Bash"]
        assert [c.index for c in calls] == [0, 1, 2]

    def test_multiple_tool_calls_in_one_message_preserve_order(self):
        lines = [
            _assistant_event(
                [
                    _tool_use_block("Read", {"path": "a.py"}),
                    _tool_use_block("Read", {"path": "b.py"}),
                    _tool_use_block("Write", {"path": "c.py"}),
                ]
            ),
        ]

        calls = extract_tool_calls(lines)

        assert [c.name for c in calls] == ["Read", "Read", "Write"]
        assert calls[1].input == {"path": "b.py"}

    def test_interleaved_text_and_tool_use_blocks_only_captures_tool_use(self):
        lines = [
            _assistant_event(
                [
                    _text_block("I will read the file."),
                    _tool_use_block("Read", {"path": "a.py"}),
                    _text_block("Now editing."),
                    _tool_use_block("Edit", {"path": "a.py"}),
                ]
            ),
        ]

        calls = extract_tool_calls(lines)

        assert [c.name for c in calls] == ["Read", "Edit"]

    def test_callback_invoked_live_per_tool_call(self):
        lines = [
            _assistant_event([_tool_use_block("Read", {"path": "a.py"})]),
            _assistant_event([_tool_use_block("Write", {"path": "b.py"})]),
        ]
        observed: list[ToolCall] = []

        result = extract_tool_calls(lines, on_tool_call=observed.append)

        assert observed == result
        assert [c.name for c in observed] == ["Read", "Write"]

    def test_malformed_json_line_skipped_not_raised(self):
        lines = [
            "not json {{{",
            _assistant_event([_tool_use_block("Read", {"path": "a.py"})]),
        ]

        calls = extract_tool_calls(lines)

        assert [c.name for c in calls] == ["Read"]

    def test_spike_does_not_import_production_subprocess_utils(self):
        source = Path(__file__).parent.joinpath("trace_capture.py").read_text()
        tree = ast.parse(source)
        imported_modules = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_modules.add(node.module)

        assert not any(m.startswith("little_loops") for m in imported_modules), (
            "trace_capture.py must not import production little_loops modules"
        )
