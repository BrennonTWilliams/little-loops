"""Tests for ll-loop run persistent default flags via config (ENH-2109)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


class TestLoopRunDefaults:
    """Tests that ll-loop run backfills args from loops.run_defaults config."""

    def _write_config(self, tmp_path: Path, run_defaults: dict) -> None:
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir(exist_ok=True)
        config = {"loops": {"run_defaults": run_defaults}}
        (ll_dir / "ll-config.json").write_text(json.dumps(config))

    def test_clear_default_applied_from_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Config clear:true backfills args.clear when --clear is not passed on CLI."""
        self._write_config(tmp_path, {"clear": True})
        monkeypatch.chdir(tmp_path)

        with (
            patch.object(sys, "argv", ["ll-loop", "run", "my-loop"]),
            patch("little_loops.cli.loop.run.cmd_run", return_value=0) as mock_run,
        ):
            from little_loops.cli import main_loop

            main_loop()

        args = mock_run.call_args[0][1]
        assert args.clear is True

    def test_explicit_clear_not_overridden_by_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Explicit --clear on CLI is not affected by config clear:false."""
        self._write_config(tmp_path, {"clear": False})
        monkeypatch.chdir(tmp_path)

        with (
            patch.object(sys, "argv", ["ll-loop", "run", "my-loop", "--clear"]),
            patch("little_loops.cli.loop.run.cmd_run", return_value=0) as mock_run,
        ):
            from little_loops.cli import main_loop

            main_loop()

        args = mock_run.call_args[0][1]
        assert args.clear is True

    def test_show_diagrams_default_applied_from_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Config show_diagrams:'clean' backfills args.show_diagrams when flag not passed."""
        self._write_config(tmp_path, {"show_diagrams": "clean"})
        monkeypatch.chdir(tmp_path)

        with (
            patch.object(sys, "argv", ["ll-loop", "run", "my-loop"]),
            patch("little_loops.cli.loop.run.cmd_run", return_value=0) as mock_run,
        ):
            from little_loops.cli import main_loop

            main_loop()

        args = mock_run.call_args[0][1]
        assert args.show_diagrams == "clean"

    def test_explicit_show_diagrams_overrides_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Explicit --show-diagrams on CLI is not replaced by config show_diagrams."""
        self._write_config(tmp_path, {"show_diagrams": "clean"})
        monkeypatch.chdir(tmp_path)

        with (
            patch.object(
                sys,
                "argv",
                ["ll-loop", "run", "my-loop", "--show-diagrams", "detailed"],
            ),
            patch("little_loops.cli.loop.run.cmd_run", return_value=0) as mock_run,
        ):
            from little_loops.cli import main_loop

            main_loop()

        args = mock_run.call_args[0][1]
        assert args.show_diagrams == "detailed"

    def test_show_diagrams_default_sentinel_maps_to_true(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Config show_diagrams:'default' backfills args.show_diagrams=True (bare flag)."""
        self._write_config(tmp_path, {"show_diagrams": "default"})
        monkeypatch.chdir(tmp_path)

        with (
            patch.object(sys, "argv", ["ll-loop", "run", "my-loop"]),
            patch("little_loops.cli.loop.run.cmd_run", return_value=0) as mock_run,
        ):
            from little_loops.cli import main_loop

            main_loop()

        args = mock_run.call_args[0][1]
        assert args.show_diagrams is True

    def test_invalid_show_diagrams_in_config_raises_value_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Invalid show_diagrams value in config raises ValueError at config load."""
        self._write_config(tmp_path, {"show_diagrams": "not-a-valid-mode"})
        monkeypatch.chdir(tmp_path)

        with patch.object(sys, "argv", ["ll-loop", "run", "my-loop"]):
            from little_loops.cli import main_loop

            with pytest.raises(ValueError, match="show_diagrams"):
                main_loop()

    def test_delay_default_applied_from_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Config delay:2.5 backfills args.delay when --delay not passed on CLI."""
        self._write_config(tmp_path, {"delay": 2.5})
        monkeypatch.chdir(tmp_path)

        with (
            patch.object(sys, "argv", ["ll-loop", "run", "my-loop"]),
            patch("little_loops.cli.loop.run.cmd_run", return_value=0) as mock_run,
        ):
            from little_loops.cli import main_loop

            main_loop()

        args = mock_run.call_args[0][1]
        assert args.delay == 2.5

    def test_explicit_delay_overrides_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Explicit --delay on CLI is not replaced by config delay."""
        self._write_config(tmp_path, {"delay": 2.5})
        monkeypatch.chdir(tmp_path)

        with (
            patch.object(sys, "argv", ["ll-loop", "run", "my-loop", "--delay", "7"]),
            patch("little_loops.cli.loop.run.cmd_run", return_value=0) as mock_run,
        ):
            from little_loops.cli import main_loop

            main_loop()

        args = mock_run.call_args[0][1]
        assert args.delay == 7.0

    def test_no_delay_in_config_leaves_args_delay_none(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Absent delay config key leaves args.delay at its None default (no injection)."""
        self._write_config(tmp_path, {"clear": True})
        monkeypatch.chdir(tmp_path)

        with (
            patch.object(sys, "argv", ["ll-loop", "run", "my-loop"]),
            patch("little_loops.cli.loop.run.cmd_run", return_value=0) as mock_run,
        ):
            from little_loops.cli import main_loop

            main_loop()

        args = mock_run.call_args[0][1]
        assert args.delay is None

    def test_invalid_delay_in_config_raises_value_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Negative delay value in config raises ValueError at config load."""
        self._write_config(tmp_path, {"delay": -1})
        monkeypatch.chdir(tmp_path)

        with patch.object(sys, "argv", ["ll-loop", "run", "my-loop"]):
            from little_loops.cli import main_loop

            with pytest.raises(ValueError, match="delay"):
                main_loop()


class TestLoopRunDefaultsDataclass:
    """Tests for LoopRunDefaults dataclass parsing."""

    def test_from_dict_defaults(self) -> None:
        """Empty dict gives all-default LoopRunDefaults."""
        from little_loops.config.features import LoopRunDefaults

        result = LoopRunDefaults.from_dict({})
        assert result.clear is False
        assert result.show_diagrams is None
        assert result.mode is None
        assert result.include == ""
        assert result.delay is None

    def test_from_dict_include_set(self) -> None:
        """include:'project:*' is parsed and round-trips correctly."""
        from little_loops.config.features import LoopRunDefaults

        result = LoopRunDefaults.from_dict({"include": "project:*"})
        assert result.include == "project:*"

    def test_from_dict_include_comma_list(self) -> None:
        """include can hold comma-separated selectors."""
        from little_loops.config.features import LoopRunDefaults

        result = LoopRunDefaults.from_dict({"include": "builtin:*, project:*"})
        assert result.include == "builtin:*, project:*"

    def test_from_dict_include_empty_string(self) -> None:
        """Explicit empty string for include is accepted (means all loops visible)."""
        from little_loops.config.features import LoopRunDefaults

        result = LoopRunDefaults.from_dict({"include": ""})
        assert result.include == ""

    def test_from_dict_clear_true(self) -> None:
        """clear:true is parsed correctly."""
        from little_loops.config.features import LoopRunDefaults

        result = LoopRunDefaults.from_dict({"clear": True})
        assert result.clear is True

    def test_from_dict_show_diagrams_valid(self) -> None:
        """Valid show_diagrams values are accepted."""
        from little_loops.config.features import LoopRunDefaults

        for value in (
            "layered",
            "neighborhood",
            "inline",
            "detailed",
            "summary",
            "clean",
            "local",
            "slim",
            "oneline",
            "default",
        ):
            result = LoopRunDefaults.from_dict({"show_diagrams": value})
            assert result.show_diagrams == value

    def test_from_dict_show_diagrams_invalid_raises(self) -> None:
        """Invalid show_diagrams values raise ValueError."""
        from little_loops.config.features import LoopRunDefaults

        with pytest.raises(ValueError, match="show_diagrams"):
            LoopRunDefaults.from_dict({"show_diagrams": "bad-value"})

    def test_from_dict_delay_valid(self) -> None:
        """Non-negative delay values (int, float, zero) are accepted."""
        from little_loops.config.features import LoopRunDefaults

        for value in (0, 0.0, 1, 2.5, 30):
            result = LoopRunDefaults.from_dict({"delay": value})
            assert result.delay == value

    def test_from_dict_delay_negative_raises(self) -> None:
        """Negative delay values raise ValueError."""
        from little_loops.config.features import LoopRunDefaults

        with pytest.raises(ValueError, match="delay"):
            LoopRunDefaults.from_dict({"delay": -1})

    def test_from_dict_delay_non_numeric_raises(self) -> None:
        """Non-numeric delay values (including bool) raise ValueError."""
        from little_loops.config.features import LoopRunDefaults

        for bad in ("5", True, [1]):
            with pytest.raises(ValueError, match="delay"):
                LoopRunDefaults.from_dict({"delay": bad})

    def test_loops_config_includes_run_defaults(self) -> None:
        """LoopsConfig.from_dict parses run_defaults block including include field."""
        from little_loops.config.features import LoopsConfig

        result = LoopsConfig.from_dict(
            {
                "run_defaults": {
                    "clear": True,
                    "show_diagrams": "clean",
                    "include": "project:*",
                    "delay": 3,
                }
            }
        )
        assert result.run_defaults.clear is True
        assert result.run_defaults.show_diagrams == "clean"
        assert result.run_defaults.include == "project:*"
        assert result.run_defaults.delay == 3

    def test_show_input_defaults_true(self) -> None:
        """show_input defaults to True when unset."""
        from little_loops.config.features import LoopRunDefaults

        result = LoopRunDefaults.from_dict({})
        assert result.show_input is True

    def test_show_input_false_opt_out(self) -> None:
        """show_input: false is parsed through from config."""
        from little_loops.config.features import LoopRunDefaults

        result = LoopRunDefaults.from_dict({"show_input": False})
        assert result.show_input is False


_MINIMAL_LOOP_YAML = """\
name: test-loop
description: minimal loop for include-injection tests
initial: done
states:
  done:
    terminal: true
"""


class TestLoopRunIncludeContextInjection:
    """Tests that include config default is injected into fsm.context inside cmd_run."""

    def _write_config(self, tmp_path: Path, include: str) -> None:
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir(exist_ok=True)
        config = {"loops": {"run_defaults": {"include": include}}}
        (ll_dir / "ll-config.json").write_text(json.dumps(config))

    def _write_loop(self, tmp_path: Path) -> None:
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir(exist_ok=True)
        (loops_dir / "test-loop.yaml").write_text(_MINIMAL_LOOP_YAML)

    def test_include_injected_into_fsm_context_from_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Config include:'project:*' is injected into fsm.context before execution."""
        self._write_config(tmp_path, "project:*")
        self._write_loop(tmp_path)
        monkeypatch.chdir(tmp_path)

        captured_contexts: list[dict] = []

        def capturing_executor(fsm, **kwargs):  # type: ignore[no-untyped-def]
            captured_contexts.append(dict(fsm.context))
            raise SystemExit(0)

        with (
            patch.object(sys, "argv", ["ll-loop", "run", "test-loop"]),
            patch(
                "little_loops.fsm.persistence.PersistentExecutor", side_effect=capturing_executor
            ),
        ):
            from little_loops.cli import main_loop

            with pytest.raises(SystemExit):
                main_loop()

        assert captured_contexts, "PersistentExecutor was never constructed"
        assert captured_contexts[0].get("include") == "project:*"

    def test_cli_context_overrides_config_include(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--context include=builtin:* takes precedence over config include."""
        self._write_config(tmp_path, "project:*")
        self._write_loop(tmp_path)
        monkeypatch.chdir(tmp_path)

        captured_contexts: list[dict] = []

        def capturing_executor(fsm, **kwargs):  # type: ignore[no-untyped-def]
            captured_contexts.append(dict(fsm.context))
            raise SystemExit(0)

        with (
            patch.object(
                sys,
                "argv",
                ["ll-loop", "run", "test-loop", "--context", "include=builtin:*"],
            ),
            patch(
                "little_loops.fsm.persistence.PersistentExecutor", side_effect=capturing_executor
            ),
        ):
            from little_loops.cli import main_loop

            with pytest.raises(SystemExit):
                main_loop()

        assert captured_contexts, "PersistentExecutor was never constructed"
        assert captured_contexts[0].get("include") == "builtin:*"

    def test_empty_config_include_leaves_context_unset(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Config include:'' (or absent) does not inject include into fsm.context."""
        self._write_config(tmp_path, "")
        self._write_loop(tmp_path)
        monkeypatch.chdir(tmp_path)

        captured_contexts: list[dict] = []

        def capturing_executor(fsm, **kwargs):  # type: ignore[no-untyped-def]
            captured_contexts.append(dict(fsm.context))
            raise SystemExit(0)

        with (
            patch.object(sys, "argv", ["ll-loop", "run", "test-loop"]),
            patch(
                "little_loops.fsm.persistence.PersistentExecutor", side_effect=capturing_executor
            ),
        ):
            from little_loops.cli import main_loop

            with pytest.raises(SystemExit):
                main_loop()

        assert captured_contexts, "PersistentExecutor was never constructed"
        assert "include" not in captured_contexts[0]
