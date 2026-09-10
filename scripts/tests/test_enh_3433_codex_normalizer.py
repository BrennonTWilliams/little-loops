"""ENH-3433: Codex exec-call normalization to Claude shape.

Codex rollout JSONL is envelope-shaped (``{"type", "payload": {...}}``) with
no Claude-shaped equivalent for shell-exec calls, so every ll-signal reader
in ``cli/logs.py`` saw zero events from a Codex session. These tests pin
down ``CodexNormalizer``/``_extract_exec_cmd`` directly, against both the
committed real-capture fixture (ground truth for the exec-call shape) and
synthetic envelope sequences for the pairing edge cases the fixture doesn't
exercise (unpaired output, fallback pairing, sticky multi-exec failure,
missing call_id, non-double-quote ``cmd:`` delimiters).
"""

from __future__ import annotations

import json
from pathlib import Path

from little_loops.session_store.codex import CodexNormalizer, _command_text, _extract_exec_cmd

FIXTURES = Path(__file__).parent / "fixtures" / "codex"
INTERACTIVE_FIXTURE = FIXTURES / "rollout-interactive.jsonl"

SESSION_ID = "01a086ea-c8bc-79f1-9faa-1ce2716aa80f"
CWD = "/workspace/project"


def _load_fixture(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _new_normalizer() -> CodexNormalizer:
    return CodexNormalizer(session_id=SESSION_ID, cwd=CWD)


class TestExtractExecCmd:
    def test_matches_command_execution_ground_truth_for_all_fixture_execs(self) -> None:
        lines = _load_fixture(INTERACTIVE_FIXTURE)
        # (custom_tool_call line index, item_completed line index) pairs, 0-based.
        for call_idx, exec_idx in ((12, 13), (20, 21), (24, 25)):
            js_snippet = lines[call_idx]["payload"]["input"]
            ground_truth = lines[exec_idx]["payload"]["item"]["command"][-1]
            assert _extract_exec_cmd(js_snippet) == ground_truth

    def test_double_quoted_cmd_unescapes_quotes_and_newlines(self) -> None:
        snippet = 'tools.exec_command({ cmd: "echo \\"hi\\"\\nline2", workdir: "/w" })'
        assert _extract_exec_cmd(snippet) == 'echo "hi"\nline2'

    def test_single_quoted_cmd_is_extracted(self) -> None:
        snippet = "tools.exec_command({ cmd: 'echo hi', workdir: '/w' })"
        assert _extract_exec_cmd(snippet) == "echo hi"

    def test_single_quoted_cmd_unescapes_embedded_quote(self) -> None:
        snippet = "tools.exec_command({ cmd: 'it\\'s ok', workdir: '/w' })"
        assert _extract_exec_cmd(snippet) == "it's ok"

    def test_backtick_delimited_cmd_is_extracted(self) -> None:
        snippet = "tools.exec_command({ cmd: `echo hi`, workdir: `/w` })"
        assert _extract_exec_cmd(snippet) == "echo hi"

    def test_no_cmd_key_returns_none(self) -> None:
        assert _extract_exec_cmd("tools.some_other_call({ foo: 1 })") is None

    def test_multiple_ll_invocations_yields_first_match(self) -> None:
        snippet = 'tools.exec_command({ cmd: "ll-issues list && ll-loop run" })'
        assert _extract_exec_cmd(snippet) == "ll-issues list && ll-loop run"


class TestCommandText:
    def test_shell_lc_shape_returns_last_element_verbatim(self) -> None:
        assert _command_text(["/bin/zsh", "-lc", "echo hi; echo bye"]) == "echo hi; echo bye"

    def test_other_shapes_fall_back_to_shlex_join(self) -> None:
        assert _command_text(["echo", "hi there"]) == "echo 'hi there'"


class TestCodexNormalizerFixture:
    """Run CodexNormalizer over the real interactive fixture, line by line."""

    def _run(self) -> dict[int, dict | None]:
        normalizer = _new_normalizer()
        results: dict[int, dict | None] = {}
        for line_no, record in enumerate(_load_fixture(INTERACTIVE_FIXTURE), start=1):
            results[line_no] = normalizer(record)
        return results

    def test_first_exec_call_normalizes_to_assistant_bash_tool_use(self) -> None:
        results = self._run()
        normalized = results[13]
        assert normalized is not None
        assert normalized["type"] == "assistant"
        assert normalized["sessionId"] == SESSION_ID
        assert normalized["cwd"] == CWD
        block = normalized["message"]["content"][0]
        assert block == {
            "type": "tool_use",
            "id": "call_IXnX78lRvoEbxkhwSt9fR6uq",
            "name": "Bash",
            "input": {"command": "rg --files scripts/little_loops; sed -n '1,240p' pyproject.toml"},
        }

    def test_command_execution_item_yields_none(self) -> None:
        results = self._run()
        assert results[14] is None

    def test_failed_exec_output_flags_is_error_true_and_drops_header(self) -> None:
        results = self._run()
        normalized = results[15]
        assert normalized is not None
        assert normalized["type"] == "user"
        assert normalized["sessionId"] == SESSION_ID
        assert normalized["cwd"] == CWD
        block = normalized["message"]["content"][0]
        assert block["tool_use_id"] == "call_IXnX78lRvoEbxkhwSt9fR6uq"
        assert block["is_error"] is True
        assert all("Script completed" not in b["text"] for b in block["content"])

    def test_successful_execs_have_no_is_error_key(self) -> None:
        results = self._run()
        for line_no in (23, 27):
            block = results[line_no]["message"]["content"][0]
            assert "is_error" not in block

    def test_successful_exec_call_ids_match_output_tool_use_ids(self) -> None:
        results = self._run()
        for call_line, output_line in ((21, 23), (25, 27)):
            call_id = results[call_line]["message"]["content"][0]["id"]
            tool_use_id = results[output_line]["message"]["content"][0]["tool_use_id"]
            assert call_id == tool_use_id

    def test_non_exec_and_unrecognized_records_pass_through_as_none(self) -> None:
        results = self._run()
        lines = _load_fixture(INTERACTIVE_FIXTURE)
        for line_no, record in enumerate(lines, start=1):
            if line_no in (13, 15, 21, 23, 25, 27):
                continue
            assert results[line_no] is None, f"line {line_no} ({record.get('type')})"


class TestCodexNormalizerEdgeCases:
    def test_missing_call_id_yields_empty_string_id_never_raises(self) -> None:
        normalizer = _new_normalizer()
        record = {
            "timestamp": "2026-01-01T00:00:00Z",
            "type": "response_item",
            "payload": {"type": "custom_tool_call", "name": "exec", "input": 'cmd: "ls"'},
        }
        normalized = normalizer(record)
        assert normalized is not None
        assert normalized["message"]["content"][0]["id"] == ""

    def test_unrecognizable_snippet_still_emits_assistant_with_raw_snippet(self) -> None:
        normalizer = _new_normalizer()
        record = {
            "timestamp": "2026-01-01T00:00:00Z",
            "type": "response_item",
            "payload": {
                "type": "custom_tool_call",
                "name": "exec",
                "call_id": "call_x",
                "input": "not a recognizable snippet at all",
            },
        }
        normalized = normalizer(record)
        assert normalized is not None
        assert (
            normalized["message"]["content"][0]["input"]["command"]
            == "not a recognizable snippet at all"
        )

    def test_non_exec_custom_tool_call_passes_through(self) -> None:
        normalizer = _new_normalizer()
        record = {
            "timestamp": "2026-01-01T00:00:00Z",
            "type": "response_item",
            "payload": {"type": "custom_tool_call", "name": "apply_patch", "call_id": "call_x"},
        }
        assert normalizer(record) is None

    def test_output_with_no_preceding_command_execution_has_no_is_error_key(self) -> None:
        normalizer = _new_normalizer()
        call = {
            "timestamp": "2026-01-01T00:00:00Z",
            "type": "response_item",
            "payload": {
                "type": "custom_tool_call",
                "name": "exec",
                "call_id": "call_x",
                "input": 'cmd: "ll-issues list"',
            },
        }
        output = {
            "timestamp": "2026-01-01T00:00:01Z",
            "type": "response_item",
            "payload": {
                "type": "custom_tool_call_output",
                "call_id": "call_x",
                "output": [{"type": "input_text", "text": "some output"}],
            },
        }
        normalizer(call)
        normalized = normalizer(output)
        assert "is_error" not in normalized["message"]["content"][0]

    def test_command_execution_falls_back_to_most_recent_pending_on_no_match(self) -> None:
        normalizer = _new_normalizer()
        call = {
            "timestamp": "2026-01-01T00:00:00Z",
            "type": "response_item",
            "payload": {
                "type": "custom_tool_call",
                "name": "exec",
                "call_id": "call_x",
                "input": 'cmd: "unmatchable snippet text"',
            },
        }
        item_completed = {
            "timestamp": "2026-01-01T00:00:01Z",
            "type": "event_msg",
            "payload": {
                "type": "item_completed",
                "item": {
                    "type": "CommandExecution",
                    "command": ["/bin/zsh", "-lc", "totally different command"],
                    "status": "failed",
                    "exit_code": 1,
                },
            },
        }
        output = {
            "timestamp": "2026-01-01T00:00:02Z",
            "type": "response_item",
            "payload": {
                "type": "custom_tool_call_output",
                "call_id": "call_x",
                "output": [{"type": "input_text", "text": "output"}],
            },
        }
        normalizer(call)
        normalizer(item_completed)
        normalized = normalizer(output)
        assert normalized["message"]["content"][0]["is_error"] is True

    def test_multi_exec_failure_is_sticky_across_successive_command_executions(self) -> None:
        normalizer = _new_normalizer()
        call = {
            "timestamp": "2026-01-01T00:00:00Z",
            "type": "response_item",
            "payload": {
                "type": "custom_tool_call",
                "name": "exec",
                "call_id": "call_x",
                "input": 'cmd: "first"',
            },
        }
        first_exec = {
            "timestamp": "2026-01-01T00:00:01Z",
            "type": "event_msg",
            "payload": {
                "type": "item_completed",
                "item": {
                    "type": "CommandExecution",
                    "command": ["/bin/zsh", "-lc", "first"],
                    "status": "failed",
                    "exit_code": 1,
                },
            },
        }
        second_exec = {
            "timestamp": "2026-01-01T00:00:02Z",
            "type": "event_msg",
            "payload": {
                "type": "item_completed",
                "item": {
                    "type": "CommandExecution",
                    "command": ["/bin/zsh", "-lc", "second"],
                    "status": "completed",
                    "exit_code": 0,
                },
            },
        }
        output = {
            "timestamp": "2026-01-01T00:00:03Z",
            "type": "response_item",
            "payload": {
                "type": "custom_tool_call_output",
                "call_id": "call_x",
                "output": [{"type": "input_text", "text": "output"}],
            },
        }
        normalizer(call)
        normalizer(first_exec)
        normalizer(second_exec)
        normalized = normalizer(output)
        assert normalized["message"]["content"][0]["is_error"] is True

    def test_state_is_popped_after_output_bounded_memory(self) -> None:
        normalizer = _new_normalizer()
        call = {
            "timestamp": "2026-01-01T00:00:00Z",
            "type": "response_item",
            "payload": {
                "type": "custom_tool_call",
                "name": "exec",
                "call_id": "call_x",
                "input": 'cmd: "ls"',
            },
        }
        output = {
            "timestamp": "2026-01-01T00:00:01Z",
            "type": "response_item",
            "payload": {
                "type": "custom_tool_call_output",
                "call_id": "call_x",
                "output": [{"type": "input_text", "text": "output"}],
            },
        }
        normalizer(call)
        normalizer(output)
        assert normalizer._pending == {}
        assert normalizer._status == {}
