"""Tests for the fake host directives parser/executable (FEAT-3454)."""

from __future__ import annotations

import io
import shutil
import subprocess

import pytest

from little_loops.fake_host import (
    DEFAULT_SCRIPT,
    Directive,
    DirectivesScript,
    emit,
    parse_directives,
)
from little_loops.subprocess_utils import run_claude_command


@pytest.fixture
def isolated_env(monkeypatch: pytest.MonkeyPatch):
    """Clear host env vars so this test starts from a known state (test_host_runner.py precedent)."""
    monkeypatch.delenv("LL_HOST_CLI", raising=False)
    monkeypatch.delenv("LL_HOOK_HOST", raising=False)
    yield


def _script(*lines: str, preamble: str = "") -> str:
    body = "\n".join(lines)
    prefix = f"{preamble}\n" if preamble else ""
    return f"{prefix}@@fake\n{body}\n@@end"


class _FlushCountingStream(io.StringIO):
    def __init__(self) -> None:
        super().__init__()
        self.flush_count = 0

    def flush(self) -> None:
        self.flush_count += 1
        super().flush()


# -- parse_directives: no fence / default -----------------------------------


class TestParseDirectivesNoFence:
    def test_no_fence_returns_default_script(self) -> None:
        assert parse_directives("just a normal prompt, @path/to/file mentioned") is DEFAULT_SCRIPT

    def test_default_script_has_init_text_result(self) -> None:
        kinds = [d.kind for d in DEFAULT_SCRIPT.directives]
        assert kinds == ["init", "text", "result"]

    def test_default_script_init_carries_model_and_session(self) -> None:
        init = DEFAULT_SCRIPT.directives[0]
        assert init.args["model"]
        assert init.args["session"]


# -- parse_directives: comments / blank lines / fencing ----------------------


class TestParseDirectivesFencing:
    def test_blank_lines_and_comments_skipped(self) -> None:
        script = parse_directives(
            _script(
                "",
                "# a comment",
                "init model=m session=s",
                "  ",
                "text hello",
                "result",
            )
        )
        assert [d.kind for d in script.directives] == ["init", "text", "result"]

    def test_real_prompt_precedes_fence(self) -> None:
        script = parse_directives(_script("text hi", "result", preamble="@path/to/file is real"))
        assert [d.kind for d in script.directives] == ["text", "result"]

    def test_unterminated_fence_raises(self) -> None:
        with pytest.raises(ValueError, match="line 1"):
            parse_directives("@@fake\ntext hi\n")


# -- Each directive kind ------------------------------------------------------


class TestDirectiveKinds:
    def test_init_directive(self) -> None:
        script = parse_directives(_script("init model=claude-3 session=abc123"))
        d = script.directives[0]
        assert d.kind == "init"
        assert d.args == {"model": "claude-3", "session": "abc123"}

    def test_init_directive_bare(self) -> None:
        script = parse_directives(_script("init", "result"))
        d = script.directives[0]
        assert d.args == {}

    def test_text_directive_unescapes_newline(self) -> None:
        script = parse_directives(_script(r"text working\nmore lines"))
        d = script.directives[0]
        assert d.args["text"] == "working\nmore lines"

    def test_text_directive_requires_value(self) -> None:
        with pytest.raises(ValueError, match="line 2"):
            parse_directives(_script("text"))

    def test_tool_directive_with_json_input(self) -> None:
        script = parse_directives(_script('tool Read {"file_path": "/tmp/x"}'))
        d = script.directives[0]
        assert d.kind == "tool"
        assert d.args["name"] == "Read"
        assert d.args["input"] == {"file_path": "/tmp/x"}

    def test_tool_directive_without_json_input(self) -> None:
        script = parse_directives(_script("tool Bash"))
        d = script.directives[0]
        assert d.args == {"name": "Bash"}

    def test_tool_directive_invalid_json_raises(self) -> None:
        with pytest.raises(ValueError, match="line 2"):
            parse_directives(_script("tool Read {not json}"))

    def test_result_directive_full(self) -> None:
        script = parse_directives(_script("result in=10 out=20 cache=5"))
        d = script.directives[0]
        assert d.args == {"in": "10", "out": "20", "cache": "5"}

    def test_result_directive_error(self) -> None:
        script = parse_directives(_script("result error=boom"))
        d = script.directives[0]
        assert d.args["error"] == "boom"

    def test_result_directive_error_with_spaces(self) -> None:
        script = parse_directives(_script("result error=connection reset by peer"))
        d = script.directives[0]
        assert d.args["error"] == "connection reset by peer"

    def test_result_directive_structured(self) -> None:
        script = parse_directives(_script('result structured={"verdict":"pass"}'))
        d = script.directives[0]
        assert d.args["structured"] == '{"verdict":"pass"}'

    def test_result_directive_bare(self) -> None:
        script = parse_directives(_script("result"))
        assert script.directives[0].args == {}

    def test_turn_completed_directive(self) -> None:
        script = parse_directives(_script("turn_completed in=1 out=2 cached=3"))
        d = script.directives[0]
        assert d.kind == "turn_completed"
        assert d.args == {"in": "1", "out": "2", "cached": "3"}

    def test_raw_directive(self) -> None:
        script = parse_directives(_script("raw not-json-at-all", "exit 1"))
        d = script.directives[0]
        assert d.kind == "raw"
        assert d.args["text"] == "not-json-at-all"

    def test_stderr_directive(self) -> None:
        script = parse_directives(_script("stderr something went wrong", "exit 1"))
        d = script.directives[0]
        assert d.kind == "stderr"
        assert d.args["text"] == "something went wrong"

    def test_sleep_directive(self) -> None:
        script = parse_directives(_script("sleep 0.5", "result"))
        d = script.directives[0]
        assert d.kind == "sleep"
        assert d.args["seconds"] == "0.5"

    def test_sleep_directive_rejects_non_numeric(self) -> None:
        with pytest.raises(ValueError, match="line 2"):
            parse_directives(_script("sleep soon"))

    def test_exit_directive(self) -> None:
        script = parse_directives(_script("text hi", "exit 7"))
        assert script.exit_code == 7

    def test_exit_directive_rejects_non_integer(self) -> None:
        with pytest.raises(ValueError, match="line 2"):
            parse_directives(_script("exit soon"))

    def test_hang_directive(self) -> None:
        script = parse_directives(_script("result", "hang"))
        assert script.directives[-1].kind == "hang"

    def test_hang_directive_rejects_arguments(self) -> None:
        with pytest.raises(ValueError, match="line 2"):
            parse_directives(_script("hang now"))

    def test_unknown_directive_raises_with_line_number(self) -> None:
        with pytest.raises(ValueError, match="line 3"):
            parse_directives(_script("init", "bogus directive"))


# -- Terminal discipline -------------------------------------------------------


class TestTerminalDiscipline:
    def test_multiple_terminals_rejected(self) -> None:
        with pytest.raises(ValueError):
            parse_directives(_script("result", "result"))

    def test_text_after_terminal_rejected(self) -> None:
        with pytest.raises(ValueError):
            parse_directives(_script("result", "text too late"))

    def test_hang_after_terminal_accepted(self) -> None:
        script = parse_directives(_script("result", "hang"))
        assert [d.kind for d in script.directives] == ["result", "hang"]

    def test_exit_after_terminal_accepted(self) -> None:
        script = parse_directives(_script("result", "exit 0"))
        assert [d.kind for d in script.directives] == ["result", "exit"]

    def test_exit_must_be_last(self) -> None:
        with pytest.raises(ValueError):
            parse_directives(_script("exit 0", "text too late"))

    def test_hang_must_be_last(self) -> None:
        with pytest.raises(ValueError):
            parse_directives(_script("hang", "text too late"))

    def test_no_terminal_is_valid(self) -> None:
        script = parse_directives(_script("stderr crashed", "exit 1"))
        assert script.terminal_index is None

    def test_direct_construction_validates_too(self) -> None:
        with pytest.raises(ValueError):
            DirectivesScript(
                directives=[
                    Directive("result", {}, 1),
                    Directive("text", {"text": "x"}, 2),
                ],
                terminal_index=None,
            )


# -- emit ----------------------------------------------------------------------


class TestEmit:
    def test_emit_flushes_every_line(self) -> None:
        script = parse_directives(_script("init model=m session=s", "text hi", "result"))
        stdout = _FlushCountingStream()
        stderr = _FlushCountingStream()
        emit(script, stdout=stdout, stderr=stderr)
        assert stdout.flush_count == 3

    def test_emit_default_script_end_to_end(self) -> None:
        stdout = _FlushCountingStream()
        stderr = _FlushCountingStream()
        code = emit(DEFAULT_SCRIPT, stdout=stdout, stderr=stderr)
        assert code == 0
        lines = [line for line in stdout.getvalue().splitlines() if line]
        assert len(lines) == 3

    def test_emit_returns_exit_code(self) -> None:
        script = parse_directives(_script("text hi", "exit 7"))
        code = emit(script, stdout=_FlushCountingStream(), stderr=_FlushCountingStream())
        assert code == 7

    def test_emit_raw_is_not_json(self) -> None:
        import json

        script = parse_directives(_script("raw not-json-at-all", "exit 0"))
        stdout = _FlushCountingStream()
        emit(script, stdout=stdout, stderr=_FlushCountingStream())
        line = stdout.getvalue().splitlines()[0]
        assert line == "not-json-at-all"
        with pytest.raises(json.JSONDecodeError):
            json.loads(line)

    def test_emit_result_structured_output(self) -> None:
        import json

        script = parse_directives(_script('result structured={"verdict": "pass"}'))
        stdout = _FlushCountingStream()
        emit(script, stdout=stdout, stderr=_FlushCountingStream())
        event = json.loads(stdout.getvalue().splitlines()[0])
        assert event["structured_output"] == {"verdict": "pass"}

    def test_emit_stderr_goes_to_stderr(self) -> None:
        script = parse_directives(_script("stderr oops", "exit 1"))
        stdout = _FlushCountingStream()
        stderr = _FlushCountingStream()
        emit(script, stdout=stdout, stderr=stderr)
        assert stdout.getvalue() == ""
        assert stderr.getvalue().strip() == "oops"


# -- Executable smoke test ------------------------------------------------------


class TestExecutableSmoke:
    def test_ll_fake_host_on_path(self) -> None:
        assert shutil.which("ll-fake-host") is not None, (
            "ll-fake-host not found on PATH — run `pip install -e ./scripts[dev]`"
        )

    def test_ll_fake_host_default_emission(self) -> None:
        if shutil.which("ll-fake-host") is None:
            pytest.fail("ll-fake-host not found on PATH — run `pip install -e ./scripts[dev]`")
        result = subprocess.run(
            ["ll-fake-host", "a plain prompt with no fence"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        lines = [line for line in result.stdout.splitlines() if line]
        assert len(lines) == 3

    def test_ll_fake_host_scripted_emission(self) -> None:
        if shutil.which("ll-fake-host") is None:
            pytest.fail("ll-fake-host not found on PATH — run `pip install -e ./scripts[dev]`")
        prompt = _script("init model=m session=s", "text hello", "result in=1 out=1", "exit 3")
        result = subprocess.run(
            ["ll-fake-host", prompt],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 3
        lines = [line for line in result.stdout.splitlines() if line]
        assert len(lines) == 3


# -- End-to-end through run_claude_command (unpatched Popen) -------------------


class TestRunClaudeCommandEndToEnd:
    def test_default_emission_drives_callbacks(
        self, monkeypatch: pytest.MonkeyPatch, isolated_env: None
    ) -> None:
        if shutil.which("ll-fake-host") is None:
            pytest.fail("ll-fake-host not found on PATH — run `pip install -e ./scripts[dev]`")
        monkeypatch.setenv("LL_HOST_CLI", "fake")

        models: list[str] = []
        session_ids: list[str] = []
        usage_calls: list[tuple[int, int]] = []
        result_seen: list[bool] = []

        result = run_claude_command(
            "any prompt, no @@fake fence needed",
            timeout=10,
            on_model_detected=models.append,
            on_session_id_detected=session_ids.append,
            on_usage_detailed=lambda u: usage_calls.append((u.input_tokens, u.output_tokens)),
            on_result_seen=result_seen.append,
        )

        assert result.returncode == 0
        assert result.stdout == "ok"
        assert models == ["fake-model"]
        assert session_ids == ["fake-session"]
        assert len(usage_calls) == 1
        assert result_seen == [True]
