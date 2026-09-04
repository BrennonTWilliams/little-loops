"""Tests for FEAT-1931: TerminalAdapter, the stdin/stdout CommunicationAdapter.

Uses a real ``os.pipe()`` (not ``StringIO``) for stdin injection because
``selectors`` requires a real file-descriptor-backed object; the spike at
``scripts/tests/spike/terminal_hitl_await/`` proved the same fixture shape.
"""

from __future__ import annotations

import io
import os
import time

import pytest

from little_loops.fsm.adapters.terminal_adapter import TerminalAdapter
from little_loops.fsm.communication_adapter import AdapterResponse, TimeoutResponse
from little_loops.fsm.executor import FSMExecutor
from little_loops.fsm.schema import FSMLoop, StateConfig


@pytest.fixture
def pipe():
    r_fd, w_fd = os.pipe()
    reader = os.fdopen(r_fd, "r")
    writer = os.fdopen(w_fd, "w")
    yield reader, writer
    for f in (reader, writer):
        if not f.closed:
            f.close()


def make_adapter(pipe) -> tuple[TerminalAdapter, io.StringIO]:
    reader, _writer = pipe
    stdout = io.StringIO()
    return TerminalAdapter(stdin=reader, stdout=stdout), stdout


class TestSendAlert:
    def test_prompt_format_includes_loop_state_prompt_context(self, pipe) -> None:
        adapter, stdout = make_adapter(pipe)
        alert_id = adapter.send_alert(
            loop_name="my-loop",
            state_name="review",
            prompt="Approve this change?",
            captured_context={"foo": "bar"},
        )
        assert isinstance(alert_id, str) and alert_id
        output = stdout.getvalue()
        assert "my-loop" in output
        assert "review" in output
        assert "Approve this change?" in output
        assert "foo=bar" in output
        assert "y/yes/approve" in output

    def test_deadline_renders_remaining_seconds_when_present(self, pipe) -> None:
        adapter, stdout = make_adapter(pipe)
        adapter.send_alert(
            loop_name="l",
            state_name="s",
            prompt="p",
            captured_context={"deadline": time.monotonic() + 30},
        )
        assert "Time remaining" in stdout.getvalue()

    def test_no_deadline_key_omits_remaining_seconds(self, pipe) -> None:
        adapter, stdout = make_adapter(pipe)
        adapter.send_alert(loop_name="l", state_name="s", prompt="p", captured_context={})
        assert "Time remaining" not in stdout.getvalue()


class TestVerdictParsing:
    def test_approve_full_word(self, pipe) -> None:
        adapter, _stdout = make_adapter(pipe)
        _reader, writer = pipe
        alert_id = adapter.send_alert("l", "s", "p", {})
        writer.write("approve\n")
        writer.flush()
        result = adapter.await_response(alert_id, timeout=2.0)
        assert result == AdapterResponse(verdict="approve")

    def test_approve_prefix_y(self, pipe) -> None:
        adapter, _stdout = make_adapter(pipe)
        _reader, writer = pipe
        alert_id = adapter.send_alert("l", "s", "p", {})
        writer.write("y\n")
        writer.flush()
        result = adapter.await_response(alert_id, timeout=2.0)
        assert result == AdapterResponse(verdict="approve")

    def test_reject_prefix_n(self, pipe) -> None:
        adapter, _stdout = make_adapter(pipe)
        _reader, writer = pipe
        alert_id = adapter.send_alert("l", "s", "p", {})
        writer.write("n\n")
        writer.flush()
        result = adapter.await_response(alert_id, timeout=2.0)
        assert result == AdapterResponse(verdict="reject")

    def test_reject_with_trailing_reason(self, pipe) -> None:
        adapter, _stdout = make_adapter(pipe)
        _reader, writer = pipe
        alert_id = adapter.send_alert("l", "s", "p", {})
        writer.write("n too risky\n")
        writer.flush()
        result = adapter.await_response(alert_id, timeout=2.0)
        assert result == AdapterResponse(verdict="reject", reason="too risky")

    def test_approve_trailing_text_ignored(self, pipe) -> None:
        adapter, _stdout = make_adapter(pipe)
        _reader, writer = pipe
        alert_id = adapter.send_alert("l", "s", "p", {})
        writer.write("approve looks fine\n")
        writer.flush()
        result = adapter.await_response(alert_id, timeout=2.0)
        assert result == AdapterResponse(verdict="approve")

    def test_case_insensitive(self, pipe) -> None:
        adapter, _stdout = make_adapter(pipe)
        _reader, writer = pipe
        alert_id = adapter.send_alert("l", "s", "p", {})
        writer.write("YES\n")
        writer.flush()
        result = adapter.await_response(alert_id, timeout=2.0)
        assert result == AdapterResponse(verdict="approve")


class TestUnrecognizedAndEmptyInput:
    def test_unrecognized_input_prints_hint_and_stays_pending(self, pipe) -> None:
        adapter, stdout = make_adapter(pipe)
        _reader, writer = pipe
        alert_id = adapter.send_alert("l", "s", "p", {})
        writer.write("banana\n")
        writer.flush()
        result = adapter.await_response(alert_id, timeout=2.0)
        assert isinstance(result, TimeoutResponse)
        assert "Expected" in stdout.getvalue()
        assert alert_id in adapter._pending

    def test_empty_line_stays_pending_no_default(self, pipe) -> None:
        adapter, _stdout = make_adapter(pipe)
        _reader, writer = pipe
        alert_id = adapter.send_alert("l", "s", "p", {})
        writer.write("\n")
        writer.flush()
        result = adapter.await_response(alert_id, timeout=2.0)
        assert isinstance(result, TimeoutResponse)
        assert alert_id in adapter._pending


class TestEditFlow:
    def test_edit_prompts_and_returns_edited_text(self, pipe) -> None:
        adapter, stdout = make_adapter(pipe)
        _reader, writer = pipe
        alert_id = adapter.send_alert("l", "s", "p", {})
        writer.write("e\n")
        writer.write("replacement text\n")
        writer.flush()
        result = adapter.await_response(alert_id, timeout=2.0)
        assert result == AdapterResponse(verdict="edit", edited_text="replacement text")
        assert "Enter replacement text" in stdout.getvalue()
        assert alert_id not in adapter._pending

    def test_edit_second_read_timeout_resumes_on_next_call(self, pipe) -> None:
        adapter, _stdout = make_adapter(pipe)
        reader, writer = pipe
        alert_id = adapter.send_alert("l", "s", "p", {})
        writer.write("edit\n")
        writer.flush()
        first = adapter.await_response(alert_id, timeout=0.3)
        assert isinstance(first, TimeoutResponse)
        assert adapter._pending[alert_id].awaiting_edit_text is True

        writer.write("late text\n")
        writer.flush()
        second = adapter.await_response(alert_id, timeout=2.0)
        assert second == AdapterResponse(verdict="edit", edited_text="late text")
        assert alert_id not in adapter._pending


class TestReadAhead:
    def test_two_lines_written_before_either_read_both_resolve_correctly(self, pipe) -> None:
        """Regression: a naive selectors-select-before-every-readline() approach
        misses this — TextIOWrapper's internal read-ahead can pull both lines
        off the fd on the first readline(), leaving nothing for the second
        call's select() to see even though a line is already buffered.
        """
        adapter, _stdout = make_adapter(pipe)
        _reader, writer = pipe
        alert_1 = adapter.send_alert("l", "s1", "p1", {})
        alert_2 = adapter.send_alert("l", "s2", "p2", {})
        writer.write("approve\n")
        writer.write("reject too risky\n")
        writer.flush()

        result_1 = adapter.await_response(alert_1, timeout=2.0)
        result_2 = adapter.await_response(alert_2, timeout=2.0)

        assert result_1 == AdapterResponse(verdict="approve")
        assert result_2 == AdapterResponse(verdict="reject", reason="too risky")


class TestTimeout:
    def test_pure_timeout_returns_timeout_response(self, pipe) -> None:
        adapter, _stdout = make_adapter(pipe)
        alert_id = adapter.send_alert("l", "s", "p", {})
        start = time.monotonic()
        result = adapter.await_response(alert_id, timeout=0.3)
        elapsed = time.monotonic() - start
        assert isinstance(result, TimeoutResponse)
        assert elapsed < 1.0
        assert alert_id in adapter._pending

    def test_unknown_alert_id_raises_key_error(self, pipe) -> None:
        adapter, _stdout = make_adapter(pipe)
        with pytest.raises(KeyError):
            adapter.await_response("nonexistent", timeout=0.1)


class TestEofLatch:
    def test_eof_latches_and_subsequent_calls_sleep_then_timeout(self, pipe) -> None:
        adapter, _stdout = make_adapter(pipe)
        reader, writer = pipe
        alert_id = adapter.send_alert("l", "s", "p", {})
        writer.close()  # closing the write end triggers EOF on reader

        first = adapter.await_response(alert_id, timeout=2.0)
        assert isinstance(first, TimeoutResponse)
        assert adapter._stdin_closed is True

        start = time.monotonic()
        second = adapter.await_response(alert_id, timeout=0.3)
        elapsed = time.monotonic() - start
        assert isinstance(second, TimeoutResponse)
        assert elapsed >= 0.25  # slept for ~timeout, did not busy-loop


class TestCancelAlert:
    def test_cancel_alert_prints_notice_and_clears_pending(self, pipe) -> None:
        adapter, stdout = make_adapter(pipe)
        alert_id = adapter.send_alert("l", "s", "p", {})
        adapter.cancel_alert(alert_id)
        assert alert_id not in adapter._pending
        assert "withdrawn" in stdout.getvalue().lower()

    def test_cancel_alert_noop_for_unknown_id(self, pipe) -> None:
        adapter, stdout = make_adapter(pipe)
        adapter.cancel_alert("nonexistent")
        assert stdout.getvalue() == ""


class TestSupportsAsync:
    def test_returns_false(self, pipe) -> None:
        adapter, _stdout = make_adapter(pipe)
        assert adapter.supports_async() is False


class TestZeroConfigResolution:
    def test_resolve_communication_adapter_seeds_terminal_by_default(self, tmp_path) -> None:
        fsm = FSMLoop(
            name="test",
            initial="done",
            states={"done": StateConfig(terminal=True)},
        )
        executor = FSMExecutor(fsm, working_dir=tmp_path)
        assert executor._contributed_adapters == {}

        adapter = executor.resolve_communication_adapter()

        assert isinstance(adapter, TerminalAdapter)
        assert executor._contributed_adapters["terminal"] is adapter

    def test_extension_registered_terminal_adapter_overrides_builtin(self, tmp_path) -> None:
        fsm = FSMLoop(
            name="test",
            initial="done",
            states={"done": StateConfig(terminal=True)},
        )
        executor = FSMExecutor(fsm, working_dir=tmp_path)
        sentinel = TerminalAdapter()
        executor._contributed_adapters["terminal"] = sentinel

        adapter = executor.resolve_communication_adapter()

        assert adapter is sentinel
