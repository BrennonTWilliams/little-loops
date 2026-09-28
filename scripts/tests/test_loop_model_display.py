"""ENH-3638: hint-resolved model selection in the ll-loop header."""

from __future__ import annotations

import argparse
from unittest.mock import patch

import pytest

from little_loops.cli.loop.feed import StateFeedRenderer
from little_loops.cli.loop.header import (
    compose_model_line,
    format_model_selection,
    initial_model_display,
)
from little_loops.fsm.schema import DEFAULT_LLM_MODEL, FSMLoop, LLMConfig, StateConfig
from little_loops.host_runner import HostNotConfigured


def _fsm(**llm: object) -> FSMLoop:
    return FSMLoop(
        name="t",
        initial="start",
        states={
            "start": StateConfig(action="echo x", on_yes="done"),
            "done": StateConfig(terminal=True),
        },
        max_iterations=5,
        llm=LLMConfig(**llm),  # type: ignore[arg-type]
    )


class _Host:
    def __init__(self, name: str) -> None:
        self.name = name


class TestFormatModelSelection:
    def test_hint_renders_arrow_and_backend(self) -> None:
        assert (
            format_model_selection("coding", "sonnet", "claude-code")
            == "coding → sonnet (claude-code)"
        )

    def test_hint_without_backend(self) -> None:
        assert format_model_selection("coding", "sonnet", None) == "coding → sonnet"

    def test_literal_renders_bare_resolved(self) -> None:
        assert format_model_selection("opus", "opus", "claude-code") == "opus"

    def test_sdk_literal_alias_is_not_a_hint(self) -> None:
        assert format_model_selection("sonnet", "claude-sonnet-5", "anthropic-api") == (
            "claude-sonnet-5"
        )

    def test_literal_falls_back_to_requested(self) -> None:
        assert format_model_selection("opus", None, None) == "opus"

    def test_both_none(self) -> None:
        assert format_model_selection(None, None, None) is None


class TestComposeModelLine:
    def test_effort_after_whole_display(self) -> None:
        assert compose_model_line("coding → sonnet (claude-code)", "high") == (
            "coding → sonnet (claude-code) H"
        )

    def test_no_effort_unchanged(self) -> None:
        assert compose_model_line("x", None) == "x"

    def test_none_display(self) -> None:
        assert compose_model_line(None, "high") is None


class TestInitialModelDisplay:
    def test_run_model_wins(self) -> None:
        fsm = _fsm(model_hint="coding")
        assert initial_model_display(fsm, "opus", None) == "opus"

    def test_no_hint_is_bare_llm_model(self) -> None:
        assert initial_model_display(_fsm(), None, None) == DEFAULT_LLM_MODEL

    def test_hint_resolves_against_host(self) -> None:
        fsm = _fsm(model_hint="coding")
        with patch("little_loops.cli.loop.header.resolve_host", return_value=_Host("claude-code")):
            out = initial_model_display(fsm, None, None)
        assert out is not None and out.startswith("coding → ") and out.endswith("(claude-code)")

    def test_overrides_applied(self) -> None:
        fsm = _fsm(model_hint="coding")
        with patch("little_loops.cli.loop.header.resolve_host", return_value=_Host("claude-code")):
            out = initial_model_display(fsm, None, {"claude-code": {"coding": "my-model"}})
        assert out == "coding → my-model (claude-code)"

    def test_disabled_mapping_is_unresolved(self) -> None:
        fsm = _fsm(model_hint="coding")
        with patch("little_loops.cli.loop.header.resolve_host", return_value=_Host("claude-code")):
            out = initial_model_display(fsm, None, {"claude-code": {"coding": False}})
        assert out == "coding (unresolved on claude-code)"

    def test_unsupported_backend_is_unresolved(self) -> None:
        fsm = _fsm(model_hint="coding")
        with patch("little_loops.cli.loop.header.resolve_host", return_value=_Host("opencode")):
            assert initial_model_display(fsm, None, None) == "coding (unresolved on opencode)"

    def test_no_host_cli_never_raises(self) -> None:
        fsm = _fsm(model_hint="coding")
        with patch("little_loops.cli.loop.header.resolve_host", side_effect=HostNotConfigured("x")):
            assert initial_model_display(fsm, None, None) == "coding (unresolved: no host CLI)"


def _renderer(display: str | None) -> StateFeedRenderer:
    args = argparse.Namespace(
        quiet=True,
        verbose=False,
        show_diagrams=None,
        clear=False,
        no_llm=False,
    )
    return StateFeedRenderer(_fsm(), args, model_display=display)


class TestLiveUpdate:
    def _complete(self, r: StateFeedRenderer, **fields: object) -> None:
        r.handle_event(
            {"event": "action_complete", "duration_ms": 1, "exit_code": 0, "depth": 0, **fields}
        )

    def test_selection_fields_observed_model_wins(self) -> None:
        r = _renderer("coding → sonnet (claude-code)")
        self._complete(
            r,
            model="claude-sonnet-5",
            model_requested="coding",
            model_resolved="sonnet",
            model_backend="claude-code",
        )
        assert r.model_display == "coding → claude-sonnet-5 (claude-code)"

    def test_selection_fields_without_observed_model(self) -> None:
        r = _renderer(None)
        self._complete(
            r, model_requested="coding", model_resolved="sonnet", model_backend="claude-code"
        )
        assert r.model_display == "coding → sonnet (claude-code)"

    def test_absent_fields_bare_observed_model(self) -> None:
        r = _renderer("coding → sonnet (claude-code)")
        self._complete(r, model="claude-opus-4-8")
        assert r.model_display == "claude-opus-4-8"

    def test_mixed_loop_switches_each_action(self) -> None:
        r = _renderer(None)
        self._complete(r, model="m1", model_requested="reasoning", model_resolved="m1")
        assert r.model_display == "reasoning → m1"
        self._complete(r, model="m2")
        assert r.model_display == "m2"


@pytest.mark.parametrize("effort,suffix", [(None, ""), ("high", " H")])
def test_renderer_header_carries_hint_display(
    effort: str | None, suffix: str, capsys: pytest.CaptureFixture[str]
) -> None:
    from little_loops.cli.loop.header import _render_artifact_header_lines
    from little_loops.cli.output import strip_ansi

    lines = _render_artifact_header_lines(
        _fsm(), None, "coding → sonnet (claude-code)", None, 200, effort=effort
    )
    joined = strip_ansi("\n".join(lines))
    assert f"model: coding → sonnet (claude-code){suffix}" in joined
