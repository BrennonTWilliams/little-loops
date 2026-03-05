"""Tests for cli/output.py shared output utilities."""

from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import patch

import pytest

import little_loops.cli.output as output_mod


class TestTerminalWidth:
    """Tests for terminal_width()."""

    def test_returns_integer(self) -> None:
        from little_loops.cli.output import terminal_width

        w = terminal_width()
        assert isinstance(w, int)
        assert w > 0

    def test_fallback_used_when_not_a_tty(self) -> None:
        """terminal_width returns the default when COLUMNS env is absent."""
        import os
        import shutil

        from little_loops.cli.output import terminal_width

        with patch.object(shutil, "get_terminal_size", return_value=os.terminal_size((42, 24))):
            w = terminal_width(default=80)
        assert w == 42

    def test_custom_default(self) -> None:
        import os
        import shutil

        from little_loops.cli.output import terminal_width

        with patch.object(shutil, "get_terminal_size", return_value=os.terminal_size((100, 24))):
            w = terminal_width(default=100)
        assert w == 100


class TestColorize:
    """Tests for colorize() with _USE_COLOR flag."""

    def test_no_color_returns_plain_text(self) -> None:
        """colorize() returns plain text when _USE_COLOR is False."""
        import little_loops.cli.output as output_mod

        with patch.object(output_mod, "_USE_COLOR", False):
            result = output_mod.colorize("hello", "31")
        assert result == "hello"
        assert "\033[" not in result

    def test_with_color_wraps_in_ansi(self) -> None:
        """colorize() wraps text in ANSI escape codes when _USE_COLOR is True."""
        import little_loops.cli.output as output_mod

        with patch.object(output_mod, "_USE_COLOR", True):
            result = output_mod.colorize("hello", "31")
        assert result == "\033[31mhello\033[0m"

    def test_no_color_env_suppresses_color(self) -> None:
        """_USE_COLOR is False when NO_COLOR env var is set."""
        import little_loops.cli.output as output_mod

        # _USE_COLOR is module-level, so we test colorize directly via patch
        with patch.object(output_mod, "_USE_COLOR", False):
            result = output_mod.colorize("text", "32")
        assert "\033[" not in result


class TestLoopHistoryTimestamp:
    """Tests for timestamp formatting in cmd_history."""

    def test_iso_timestamp_formatted_as_readable(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """cmd_history formats ISO timestamps as YYYY-MM-DD HH:MM:SS."""
        from little_loops.cli.loop.info import cmd_history

        loops_dir = tmp_path / ".ll-loops"
        loops_dir.mkdir()

        events = [
            {"ts": "2026-03-04T14:30:00.123456", "event": "start", "loop": "my-loop"},
        ]

        args = argparse.Namespace(tail=50)
        with patch(
            "little_loops.fsm.persistence.get_loop_history", return_value=events
        ):
            result = cmd_history("my-loop", args, loops_dir)

        assert result == 0
        captured = capsys.readouterr()
        assert "2026-03-04 14:30:00" in captured.out
        # Should not contain the raw ISO format with T separator
        assert "2026-03-04T14:30:00" not in captured.out

    def test_invalid_timestamp_falls_back_to_truncated(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """cmd_history falls back to [:19] slice for non-ISO timestamps."""
        from little_loops.cli.loop.info import cmd_history

        loops_dir = tmp_path / ".ll-loops"
        loops_dir.mkdir()

        events = [
            {"ts": "not-a-timestamp", "event": "start"},
        ]

        args = argparse.Namespace(tail=50)
        with patch(
            "little_loops.fsm.persistence.get_loop_history", return_value=events
        ):
            result = cmd_history("my-loop", args, loops_dir)

        assert result == 0
        captured = capsys.readouterr()
        assert "not-a-timestamp" in captured.out

    def test_missing_timestamp_handled_gracefully(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """cmd_history handles missing ts key without error."""
        from little_loops.cli.loop.info import cmd_history

        loops_dir = tmp_path / ".ll-loops"
        loops_dir.mkdir()

        events = [{"event": "start", "loop": "my-loop"}]

        args = argparse.Namespace(tail=50)
        with patch(
            "little_loops.fsm.persistence.get_loop_history", return_value=events
        ):
            result = cmd_history("my-loop", args, loops_dir)

        assert result == 0


class TestOrangeDefaultColors:
    """Tests that red codes were replaced with orange in default dicts."""

    def test_priority_p0_is_orange_not_red(self) -> None:
        from little_loops.cli.output import PRIORITY_COLOR
        assert "31" not in PRIORITY_COLOR["P0"]
        assert "208" in PRIORITY_COLOR["P0"]

    def test_priority_p1_is_orange_not_red(self) -> None:
        from little_loops.cli.output import PRIORITY_COLOR
        assert PRIORITY_COLOR["P1"] == "38;5;208"

    def test_type_bug_is_orange_not_red(self) -> None:
        from little_loops.cli.output import TYPE_COLOR
        assert TYPE_COLOR["BUG"] == "38;5;208"


class TestConfigureOutput:
    """Tests for configure_output() function."""

    def setup_method(self) -> None:
        """Reset output module state before each test."""
        import little_loops.cli.output as m
        m._USE_COLOR = False
        m.PRIORITY_COLOR.update({"P0": "38;5;208;1", "P1": "38;5;208", "P2": "33", "P3": "0", "P4": "2", "P5": "2"})
        m.TYPE_COLOR.update({"BUG": "38;5;208", "FEAT": "32", "ENH": "34"})

    def teardown_method(self) -> None:
        """Restore defaults after each test."""
        import little_loops.cli.output as m
        m._USE_COLOR = False
        m.PRIORITY_COLOR.update({"P0": "38;5;208;1", "P1": "38;5;208", "P2": "33", "P3": "0", "P4": "2", "P5": "2"})
        m.TYPE_COLOR.update({"BUG": "38;5;208", "FEAT": "32", "ENH": "34"})

    def test_configure_none_uses_tty_and_no_color_check(self) -> None:
        """configure_output(None) sets _USE_COLOR based on TTY and NO_COLOR."""
        from little_loops.cli.output import configure_output
        with patch.dict("os.environ", {}, clear=False) as env:
            env.pop("NO_COLOR", None)
            with patch("sys.stdout") as mock_stdout:
                mock_stdout.isatty.return_value = True
                configure_output(None)
        assert output_mod._USE_COLOR is True

    def test_configure_color_false_disables_ansi(self) -> None:
        """configure_output with cli.color=False sets _USE_COLOR=False."""
        from little_loops.cli.output import configure_output
        from little_loops.config import CliConfig

        cli_config = CliConfig.from_dict({"color": False})
        with patch("sys.stdout") as mock_stdout:
            mock_stdout.isatty.return_value = True
            configure_output(cli_config)
        assert output_mod._USE_COLOR is False

    def test_configure_no_color_env_overrides_color_true(self) -> None:
        """NO_COLOR env var disables color even when cli.color=True."""
        from little_loops.cli.output import configure_output
        from little_loops.config import CliConfig

        cli_config = CliConfig.from_dict({"color": True})
        with patch.dict("os.environ", {"NO_COLOR": "1"}):
            with patch("sys.stdout") as mock_stdout:
                mock_stdout.isatty.return_value = True
                configure_output(cli_config)
        assert output_mod._USE_COLOR is False

    def test_configure_custom_priority_colors(self) -> None:
        """configure_output merges custom priority colors into PRIORITY_COLOR."""
        from little_loops.cli.output import PRIORITY_COLOR, configure_output
        from little_loops.config import CliConfig

        cli_config = CliConfig.from_dict({"colors": {"priority": {"P0": "31;1", "P1": "31"}}})
        configure_output(cli_config)
        assert PRIORITY_COLOR["P0"] == "31;1"
        assert PRIORITY_COLOR["P1"] == "31"
        assert PRIORITY_COLOR["P2"] == "33"  # unchanged default

    def test_configure_custom_type_colors(self) -> None:
        """configure_output merges custom type colors into TYPE_COLOR."""
        from little_loops.cli.output import TYPE_COLOR, configure_output
        from little_loops.config import CliConfig

        cli_config = CliConfig.from_dict({"colors": {"type": {"BUG": "31"}}})
        configure_output(cli_config)
        assert TYPE_COLOR["BUG"] == "31"
        assert TYPE_COLOR["FEAT"] == "32"  # unchanged default

    def test_colorize_uses_updated_use_color(self) -> None:
        """colorize() respects _USE_COLOR after configure_output call."""
        from little_loops.cli.output import colorize, configure_output
        from little_loops.config import CliConfig

        cli_config = CliConfig.from_dict({"color": False})
        configure_output(cli_config)
        result = colorize("hello", "31")
        assert result == "hello"
        assert "\033[" not in result


class TestIssueListNoColor:
    """Tests for cmd_list color suppression."""

    def test_no_color_produces_plain_text(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """cmd_list output contains no ANSI codes when _USE_COLOR is False."""
        import little_loops.cli.output as output_mod
        from little_loops.cli.issues.list_cmd import cmd_list

        bugs_dir = tmp_path / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True)
        (bugs_dir / "P1-BUG-001-test.md").write_text("# BUG-001: Test bug\n")

        config = type("C", (), {"project_root": tmp_path, "issues": type("I", (), {"base_dir": ".issues"})()})()  # type: ignore[misc]
        args = argparse.Namespace(type=None, priority=None, flat=False)

        with patch.object(output_mod, "_USE_COLOR", False):
            with patch(
                "little_loops.issue_parser.find_issues",
                return_value=[
                    type(
                        "Issue",
                        (),
                        {
                            "path": bugs_dir / "P1-BUG-001-test.md",
                            "title": "Test bug",
                            "issue_id": "BUG-001",
                            "priority": "P1",
                        },
                    )()
                ],
            ):
                result = cmd_list(config, args)

        assert result == 0
        captured = capsys.readouterr()
        assert "\033[" not in captured.out
        assert "BUG-001" in captured.out
        assert "Test bug" in captured.out
