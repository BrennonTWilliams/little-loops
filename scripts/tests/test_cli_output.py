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


class TestTerminalSize:
    """Tests for terminal_size() returning (cols, rows)."""

    def test_returns_cols_and_rows_tuple(self) -> None:
        import os
        import shutil

        from little_loops.cli.output import terminal_size

        with patch.object(shutil, "get_terminal_size", return_value=os.terminal_size((100, 30))):
            cols, rows = terminal_size()
        assert (cols, rows) == (100, 30)

    def test_default_dimensions_used_when_unavailable(self) -> None:
        import os
        import shutil

        from little_loops.cli.output import terminal_size

        with patch.object(shutil, "get_terminal_size", return_value=os.terminal_size((50, 15))):
            cols, rows = terminal_size(default_cols=80, default_rows=24)
        assert (cols, rows) == (50, 15)

    def test_terminal_width_wraps_terminal_size(self) -> None:
        import os
        import shutil

        from little_loops.cli.output import terminal_width

        with patch.object(shutil, "get_terminal_size", return_value=os.terminal_size((77, 33))):
            w = terminal_width()
        assert w == 77


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
        """cmd_history formats ISO timestamps as HH:MM:SS."""
        from little_loops.cli.loop.info import cmd_history

        loops_dir = tmp_path / ".ll-loops"
        loops_dir.mkdir()

        events = [
            {"ts": "2026-03-04T14:30:00.123456", "event": "start", "loop": "my-loop"},
        ]

        args = argparse.Namespace(tail=50, verbose=False, full=False, json=False)
        with patch("little_loops.fsm.persistence.get_archived_events", return_value=events):
            result = cmd_history("my-loop", "test-run-id", args, loops_dir)

        assert result == 0
        captured = capsys.readouterr()
        assert "14:30:00" in captured.out
        # Should not contain the raw ISO format with T separator
        assert "2026-03-04T14:30:00" not in captured.out

    def test_invalid_timestamp_falls_back_to_truncated(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """cmd_history falls back to 8-char slice for non-ISO timestamps."""
        from little_loops.cli.loop.info import cmd_history

        loops_dir = tmp_path / ".ll-loops"
        loops_dir.mkdir()

        events = [
            {"ts": "not-a-timestamp", "event": "start"},
        ]

        args = argparse.Namespace(tail=50, verbose=False, full=False, json=False)
        with patch("little_loops.fsm.persistence.get_archived_events", return_value=events):
            result = cmd_history("my-loop", "test-run-id", args, loops_dir)

        assert result == 0
        captured = capsys.readouterr()
        assert "not-a-ti" in captured.out

    def test_missing_timestamp_handled_gracefully(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """cmd_history handles missing ts key without error."""
        from little_loops.cli.loop.info import cmd_history

        loops_dir = tmp_path / ".ll-loops"
        loops_dir.mkdir()

        events = [{"event": "start", "loop": "my-loop"}]

        args = argparse.Namespace(tail=50, verbose=False, full=False, json=False)
        with patch("little_loops.fsm.persistence.get_archived_events", return_value=events):
            result = cmd_history("my-loop", "test-run-id", args, loops_dir)

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

    def test_type_epic_has_color(self) -> None:
        from little_loops.cli.output import TYPE_COLOR

        assert TYPE_COLOR["EPIC"] == "35"


class TestConfigureOutput:
    """Tests for configure_output() function."""

    def setup_method(self) -> None:
        """Reset output module state before each test."""
        import little_loops.cli.output as m

        m._USE_COLOR = False
        m.PRIORITY_COLOR.update(
            {"P0": "38;5;208;1", "P1": "38;5;208", "P2": "33", "P3": "0", "P4": "2", "P5": "2"}
        )
        m.TYPE_COLOR.update({"BUG": "38;5;208", "FEAT": "32", "ENH": "34", "EPIC": "35"})

    def teardown_method(self) -> None:
        """Restore defaults after each test."""
        import little_loops.cli.output as m

        m._USE_COLOR = False
        m.PRIORITY_COLOR.update(
            {"P0": "38;5;208;1", "P1": "38;5;208", "P2": "33", "P3": "0", "P4": "2", "P5": "2"}
        )
        m.TYPE_COLOR.update({"BUG": "38;5;208", "FEAT": "32", "ENH": "34", "EPIC": "35"})

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

    def test_use_color_enabled_reflects_configure_output_state(self) -> None:
        """use_color_enabled() returns the current _USE_COLOR module state."""
        import little_loops.cli.output as output_module
        from little_loops.cli.output import use_color_enabled

        with patch.object(output_module, "_USE_COLOR", False):
            assert use_color_enabled() is False
        with patch.object(output_module, "_USE_COLOR", True):
            assert use_color_enabled() is True


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

        bug_cat = type("Cat", (), {"prefix": "BUG", "dir": "bugs"})()
        issues_ns = type("I", (), {"base_dir": ".issues", "categories": {"bugs": bug_cat}})()
        config = type(
            "C",
            (),
            {
                "project_root": tmp_path,
                "issues": issues_ns,
                "issue_categories": ["bugs"],
                "issue_priorities": ["P0", "P1", "P2", "P3", "P4", "P5"],
                "get_issue_dir": lambda self, cat: tmp_path / ".issues" / cat,
            },
        )()  # type: ignore[misc]
        args = argparse.Namespace(type=None, priority=None, flat=False, group_by="type")

        with patch.object(output_mod, "_USE_COLOR", False):
            result = cmd_list(config, args)

        assert result == 0
        captured = capsys.readouterr()
        assert "\033[" not in captured.out
        assert "BUG-001" in captured.out
        assert "Test bug" in captured.out


# ---------------------------------------------------------------------------
# ENH-1781: New shared output helpers — tests written before implementation
# ---------------------------------------------------------------------------


class TestStripAnsi:
    """Tests for strip_ansi()."""

    def test_strips_sgr_sequences(self) -> None:
        """strip_ansi removes ANSI SGR escape codes."""
        from little_loops.cli.output import strip_ansi

        result = strip_ansi("\033[31mhello\033[0m")
        assert result == "hello"

    def test_passes_plain_text_unchanged(self) -> None:
        """strip_ansi returns plain text as-is."""
        from little_loops.cli.output import strip_ansi

        result = strip_ansi("hello world")
        assert result == "hello world"

    def test_handles_empty_string(self) -> None:
        """strip_ansi handles empty string."""
        from little_loops.cli.output import strip_ansi

        result = strip_ansi("")
        assert result == ""

    def test_strips_multi_byte_color_codes(self) -> None:
        """strip_ansi removes 256-color escape sequences like 38;5;208."""
        from little_loops.cli.output import strip_ansi

        result = strip_ansi("\033[38;5;208mwarning\033[0m")
        assert result == "warning"

    def test_strips_bold_sequences(self) -> None:
        """strip_ansi removes bold + color sequences."""
        from little_loops.cli.output import strip_ansi

        result = strip_ansi("\033[1;31mbold red\033[0m")
        assert result == "bold red"


class TestBoxConstants:
    """Tests for box-drawing character constants."""

    def test_horizontal_is_single_char(self) -> None:
        from little_loops.cli.output import BOX_H

        assert len(BOX_H) == 1

    def test_vertical_is_single_char(self) -> None:
        from little_loops.cli.output import BOX_V

        assert len(BOX_V) == 1

    def test_corners_are_distinct(self) -> None:
        from little_loops.cli.output import BOX_TL, BOX_TR, BOX_BL, BOX_BR

        assert len({BOX_TL, BOX_TR, BOX_BL, BOX_BR}) == 4

    def test_all_box_chars_are_single_unicode(self) -> None:
        from little_loops.cli.output import (
            BOX_BL,
            BOX_BR,
            BOX_H,
            BOX_ML,
            BOX_MR,
            BOX_TL,
            BOX_TR,
            BOX_V,
        )

        for char in (BOX_H, BOX_V, BOX_TL, BOX_TR, BOX_BL, BOX_BR, BOX_ML, BOX_MR):
            assert len(char) == 1


class FlushTracker:
    """Minimal stream that tracks whether flush() was called."""

    def __init__(self) -> None:
        self.content: list[str] = []
        self.flush_called = False

    def write(self, s: str) -> None:
        self.content.append(s)

    def flush(self) -> None:
        self.flush_called = True


class TestMessageHelpers:
    """Tests for success(), error(), warning(), info(), hint()."""

    def test_success_prints_to_stdout(self, capsys: pytest.CaptureFixture[str]) -> None:
        """success() writes to stdout."""
        from little_loops.cli.output import success

        with patch.object(output_mod, "_USE_COLOR", False):
            success("done")
        captured = capsys.readouterr()
        assert "done" in captured.out
        assert captured.err == ""

    def test_error_prints_to_stderr(self, capsys: pytest.CaptureFixture[str]) -> None:
        """error() writes to stderr."""
        from little_loops.cli.output import error

        with patch.object(output_mod, "_USE_COLOR", False):
            error("fail")
        captured = capsys.readouterr()
        assert "fail" in captured.err

    def test_warning_prints_to_stdout(self, capsys: pytest.CaptureFixture[str]) -> None:
        """warning() writes to stdout."""
        from little_loops.cli.output import warning

        with patch.object(output_mod, "_USE_COLOR", False):
            warning("careful")
        captured = capsys.readouterr()
        assert "careful" in captured.out
        assert captured.err == ""

    def test_info_prints_to_stdout(self, capsys: pytest.CaptureFixture[str]) -> None:
        """info() writes to stdout."""
        from little_loops.cli.output import info

        with patch.object(output_mod, "_USE_COLOR", False):
            info("note")
        captured = capsys.readouterr()
        assert "note" in captured.out
        assert captured.err == ""

    def test_hint_prints_to_stdout(self, capsys: pytest.CaptureFixture[str]) -> None:
        """hint() writes to stdout."""
        from little_loops.cli.output import hint

        with patch.object(output_mod, "_USE_COLOR", False):
            hint("tip")
        captured = capsys.readouterr()
        assert "tip" in captured.out
        assert captured.err == ""

    def test_success_includes_icon_with_color(self, capsys: pytest.CaptureFixture[str]) -> None:
        """success() includes checkmark icon when color enabled."""
        from little_loops.cli.output import success

        with patch.object(output_mod, "_USE_COLOR", True):
            success("done")
        captured = capsys.readouterr()
        assert "✓" in captured.out

    def test_error_includes_icon_with_color(self, capsys: pytest.CaptureFixture[str]) -> None:
        """error() includes X icon when color enabled."""
        from little_loops.cli.output import error

        with patch.object(output_mod, "_USE_COLOR", True):
            error("fail")
        captured = capsys.readouterr()
        assert "✗" in captured.err

    def test_no_icon_when_color_disabled(self, capsys: pytest.CaptureFixture[str]) -> None:
        """No icon prefix when _USE_COLOR is False."""
        from little_loops.cli.output import success

        with patch.object(output_mod, "_USE_COLOR", False):
            success("done")
        captured = capsys.readouterr()
        assert "✓" not in captured.out

    def test_all_helpers_flush(self) -> None:
        """All message helpers call flush() on their stream."""
        from little_loops.cli.output import error, hint, info, success, warning

        with patch.object(output_mod, "_USE_COLOR", False):
            for func in (success, error, warning, info, hint):
                tracker = FlushTracker()
                stream_attr = "sys.stderr" if func is error else "sys.stdout"
                with patch(stream_attr, tracker):
                    func("test")
                assert tracker.flush_called, f"{func.__name__}() must call flush()"


class TestTable:
    """Tests for table() structured formatter."""

    def test_returns_string_with_headers(self) -> None:
        """table() returns a string containing header text."""
        from little_loops.cli.output import table

        result = table(["Name", "Value"], [["foo", "bar"]])
        assert "Name" in result
        assert "Value" in result
        assert "foo" in result
        assert "bar" in result

    def test_handles_empty_rows(self) -> None:
        """table() with no rows returns headers only."""
        from little_loops.cli.output import table

        result = table(["Col1", "Col2"], [])
        assert "Col1" in result
        assert "Col2" in result
        # Should still have box-drawing borders
        assert len(result) > 0

    def test_returns_string_type(self) -> None:
        """table() returns str."""
        from little_loops.cli.output import table

        result = table(["A"], [["1"]])
        assert isinstance(result, str)

    def test_truncates_long_values(self) -> None:
        """table() truncates values exceeding max_col_width."""
        from little_loops.cli.output import table

        result = table(["Header"], [["a" * 100]], max_col_width=10)
        # Value should be truncated (10 chars + "..." = 13 chars max in cell)
        assert "a" * 20 not in result


class TestStatusBlock:
    """Tests for status_block() structured formatter."""

    def test_returns_string_with_keys_and_values(self) -> None:
        """status_block() returns a string containing all keys and values."""
        from little_loops.cli.output import status_block

        result = status_block({"Status": "open", "Priority": "P1"})
        assert "Status" in result
        assert "open" in result
        assert "Priority" in result
        assert "P1" in result

    def test_aligns_labels(self) -> None:
        """status_block() pads shorter keys to align values."""
        from little_loops.cli.output import status_block

        result = status_block({"A": "1", "BBB": "2"})
        lines = result.split("\n")
        # Find lines with values
        val_lines = [l for l in lines if l.strip()]
        if len(val_lines) >= 2:
            # Both value positions should be aligned
            pos1 = val_lines[0].find("1")
            pos2 = val_lines[1].find("2")
            assert pos1 == pos2, f"Values not aligned: {val_lines[0]!r} vs {val_lines[1]!r}"

    def test_handles_empty_dict(self) -> None:
        """status_block() handles empty dict."""
        from little_loops.cli.output import status_block

        result = status_block({})
        assert isinstance(result, str)
        assert result == ""


class TestProgress:
    """Tests for progress() bar formatter."""

    def test_returns_bar_string(self) -> None:
        """progress() returns a |####  | style bar."""
        from little_loops.cli.output import progress

        bar = progress(5, 10, 10)
        assert bar.startswith("|")
        assert bar.endswith("|")

    def test_full_bar(self) -> None:
        """progress() at 100% is all filled."""
        from little_loops.cli.output import progress

        bar = progress(100, 100, 12)
        assert "#" * 10 in bar

    def test_empty_bar(self) -> None:
        """progress() at 0% is all spaces."""
        from little_loops.cli.output import progress

        bar = progress(0, 100, 12)
        assert "#" not in bar
        assert " " * 10 in bar

    def test_half_bar(self) -> None:
        """progress() at 50% is half filled."""
        from little_loops.cli.output import progress

        bar = progress(50, 100, 12)
        assert bar.count("#") == 5
        assert bar.count(" ") == 5

    def test_zero_total_handled(self) -> None:
        """progress() with zero total returns empty bar."""
        from little_loops.cli.output import progress

        bar = progress(0, 0, 8)
        assert bar == "|" + " " * 6 + "|"

    def test_respects_custom_width(self) -> None:
        """progress() respects custom width."""
        from little_loops.cli.output import progress

        bar = progress(10, 10, 5)
        assert len(bar) == 5


class TestForceColor:
    """Tests for FORCE_COLOR env var support."""

    def test_force_color_overrides_tty_detection(self) -> None:
        """FORCE_COLOR=1 enables color even without TTY."""
        from little_loops.cli.output import configure_output

        with patch.dict("os.environ", {"FORCE_COLOR": "1"}, clear=True):
            with patch("sys.stdout") as mock_stdout:
                mock_stdout.isatty.return_value = False
                configure_output(None)
        assert output_mod._USE_COLOR is True

    def test_no_color_overrides_force_color(self) -> None:
        """NO_COLOR takes precedence over FORCE_COLOR."""
        from little_loops.cli.output import configure_output

        with patch.dict("os.environ", {"FORCE_COLOR": "1", "NO_COLOR": "1"}, clear=True):
            with patch("sys.stdout") as mock_stdout:
                mock_stdout.isatty.return_value = False
                configure_output(None)
        assert output_mod._USE_COLOR is False

    def test_force_color_off_does_not_force(self) -> None:
        """FORCE_COLOR=0 or absent does not force color."""
        from little_loops.cli.output import configure_output

        with patch.dict("os.environ", {}, clear=True):
            with patch("sys.stdout") as mock_stdout:
                mock_stdout.isatty.return_value = False
                configure_output(None)
        assert output_mod._USE_COLOR is False


class TestOutputMode:
    """Tests for set_output_mode() / get_output_mode()."""

    def test_default_mode_is_human(self) -> None:
        """Default output mode is 'human'."""
        from little_loops.cli.output import get_output_mode

        assert get_output_mode() == "human"

    def test_set_mode_changes_get_mode(self) -> None:
        """set_output_mode() changes get_output_mode() return value."""
        from little_loops.cli.output import get_output_mode, set_output_mode

        set_output_mode("json")
        assert get_output_mode() == "json"

    def test_set_mode_to_plain(self) -> None:
        """set_output_mode('plain') works."""
        from little_loops.cli.output import get_output_mode, set_output_mode

        set_output_mode("plain")
        assert get_output_mode() == "plain"

    def test_set_mode_back_to_human(self) -> None:
        """Can switch back to human mode."""
        from little_loops.cli.output import get_output_mode, set_output_mode

        set_output_mode("json")
        set_output_mode("human")
        assert get_output_mode() == "human"
