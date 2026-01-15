"""Tests for little_loops.logger module.

Tests cover:
- Logger class initialization
- Log level methods (info, debug, success, warning, error, timing, header)
- Color and verbose configuration
- format_duration() utility function
"""

from __future__ import annotations

import re

import pytest

from little_loops.logger import Logger, format_duration

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def logger() -> Logger:
    """Fresh Logger with default settings."""
    return Logger()


@pytest.fixture
def silent_logger() -> Logger:
    """Logger with verbose=False."""
    return Logger(verbose=False)


@pytest.fixture
def no_color_logger() -> Logger:
    """Logger with use_color=False."""
    return Logger(use_color=False)


@pytest.fixture
def silent_no_color_logger() -> Logger:
    """Logger with both verbose=False and use_color=False."""
    return Logger(verbose=False, use_color=False)


# =============================================================================
# TestLoggerInit
# =============================================================================


class TestLoggerInit:
    """Tests for Logger initialization."""

    def test_default_verbose_true(self) -> None:
        """Default verbose=True."""
        log = Logger()
        assert log.verbose is True

    def test_default_use_color_true(self) -> None:
        """Default use_color=True."""
        log = Logger()
        assert log.use_color is True

    def test_accepts_verbose_false(self) -> None:
        """Can set verbose=False."""
        log = Logger(verbose=False)
        assert log.verbose is False

    def test_accepts_use_color_false(self) -> None:
        """Can set use_color=False."""
        log = Logger(use_color=False)
        assert log.use_color is False

    def test_both_flags_false(self) -> None:
        """Can set both flags to False."""
        log = Logger(verbose=False, use_color=False)
        assert log.verbose is False
        assert log.use_color is False


# =============================================================================
# TestLoggerColorConstants
# =============================================================================


class TestLoggerColorConstants:
    """Tests for color constant definitions."""

    def test_cyan_defined(self) -> None:
        """CYAN color code is defined."""
        assert Logger.CYAN == "\033[36m"

    def test_green_defined(self) -> None:
        """GREEN color code is defined."""
        assert Logger.GREEN == "\033[32m"

    def test_yellow_defined(self) -> None:
        """YELLOW color code is defined."""
        assert Logger.YELLOW == "\033[33m"

    def test_red_defined(self) -> None:
        """RED color code is defined."""
        assert Logger.RED == "\033[31m"

    def test_magenta_defined(self) -> None:
        """MAGENTA color code is defined."""
        assert Logger.MAGENTA == "\033[35m"

    def test_gray_defined(self) -> None:
        """GRAY color code is defined."""
        assert Logger.GRAY == "\033[90m"

    def test_reset_defined(self) -> None:
        """RESET color code is defined."""
        assert Logger.RESET == "\033[0m"


# =============================================================================
# TestLoggerFormatting
# =============================================================================


class TestLoggerFormatting:
    """Tests for message formatting."""

    def test_format_includes_timestamp(
        self, logger: Logger, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Output contains [HH:MM:SS] timestamp."""
        logger.info("test message")
        captured = capsys.readouterr()
        # Match timestamp pattern like [14:32:55]
        assert re.search(r"\[\d{2}:\d{2}:\d{2}\]", captured.out) is not None

    def test_format_with_color_includes_ansi(
        self, logger: Logger, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Contains ANSI codes when use_color=True."""
        logger.info("test")
        captured = capsys.readouterr()
        # Check for ANSI escape sequence
        assert "\033[" in captured.out

    def test_format_without_color_no_ansi(
        self, no_color_logger: Logger, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """No ANSI codes when use_color=False."""
        no_color_logger.info("test")
        captured = capsys.readouterr()
        assert "\033[" not in captured.out

    def test_message_appears_in_output(
        self, logger: Logger, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Message text appears in output."""
        logger.info("my specific message")
        captured = capsys.readouterr()
        assert "my specific message" in captured.out


# =============================================================================
# TestLoggerInfo
# =============================================================================


class TestLoggerInfo:
    """Tests for info() method."""

    def test_info_prints_message(self, logger: Logger, capsys: pytest.CaptureFixture[str]) -> None:
        """Message appears in output."""
        logger.info("info message")
        captured = capsys.readouterr()
        assert "info message" in captured.out

    def test_info_uses_cyan_color(self, logger: Logger, capsys: pytest.CaptureFixture[str]) -> None:
        """Uses CYAN color code."""
        logger.info("test")
        captured = capsys.readouterr()
        assert Logger.CYAN in captured.out

    def test_info_writes_to_stdout(
        self, logger: Logger, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Writes to stdout, not stderr."""
        logger.info("test")
        captured = capsys.readouterr()
        assert captured.out != ""
        assert captured.err == ""

    def test_info_silent_when_not_verbose(
        self, silent_logger: Logger, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """No output when verbose=False."""
        silent_logger.info("should not appear")
        captured = capsys.readouterr()
        assert captured.out == ""


# =============================================================================
# TestLoggerDebug
# =============================================================================


class TestLoggerDebug:
    """Tests for debug() method."""

    def test_debug_prints_message(self, logger: Logger, capsys: pytest.CaptureFixture[str]) -> None:
        """Message appears in output."""
        logger.debug("debug message")
        captured = capsys.readouterr()
        assert "debug message" in captured.out

    def test_debug_uses_gray_color(
        self, logger: Logger, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Uses GRAY color code."""
        logger.debug("test")
        captured = capsys.readouterr()
        assert Logger.GRAY in captured.out

    def test_debug_silent_when_not_verbose(
        self, silent_logger: Logger, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """No output when verbose=False."""
        silent_logger.debug("should not appear")
        captured = capsys.readouterr()
        assert captured.out == ""


# =============================================================================
# TestLoggerSuccess
# =============================================================================


class TestLoggerSuccess:
    """Tests for success() method."""

    def test_success_prints_message(
        self, logger: Logger, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Message appears in output."""
        logger.success("success message")
        captured = capsys.readouterr()
        assert "success message" in captured.out

    def test_success_uses_green_color(
        self, logger: Logger, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Uses GREEN color code."""
        logger.success("test")
        captured = capsys.readouterr()
        assert Logger.GREEN in captured.out

    def test_success_silent_when_not_verbose(
        self, silent_logger: Logger, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """No output when verbose=False."""
        silent_logger.success("should not appear")
        captured = capsys.readouterr()
        assert captured.out == ""


# =============================================================================
# TestLoggerWarning
# =============================================================================


class TestLoggerWarning:
    """Tests for warning() method."""

    def test_warning_prints_message(
        self, logger: Logger, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Message appears in output."""
        logger.warning("warning message")
        captured = capsys.readouterr()
        assert "warning message" in captured.out

    def test_warning_uses_yellow_color(
        self, logger: Logger, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Uses YELLOW color code."""
        logger.warning("test")
        captured = capsys.readouterr()
        assert Logger.YELLOW in captured.out

    def test_warning_silent_when_not_verbose(
        self, silent_logger: Logger, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """No output when verbose=False."""
        silent_logger.warning("should not appear")
        captured = capsys.readouterr()
        assert captured.out == ""


# =============================================================================
# TestLoggerError
# =============================================================================


class TestLoggerError:
    """Tests for error() method."""

    def test_error_prints_message(self, logger: Logger, capsys: pytest.CaptureFixture[str]) -> None:
        """Message appears in output."""
        logger.error("error message")
        captured = capsys.readouterr()
        assert "error message" in captured.err

    def test_error_uses_red_color(self, logger: Logger, capsys: pytest.CaptureFixture[str]) -> None:
        """Uses RED color code."""
        logger.error("test")
        captured = capsys.readouterr()
        assert Logger.RED in captured.err

    def test_error_writes_to_stderr(
        self, logger: Logger, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Writes to stderr, not stdout."""
        logger.error("test")
        captured = capsys.readouterr()
        assert captured.err != ""
        assert captured.out == ""

    def test_error_silent_when_not_verbose(
        self, silent_logger: Logger, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """No output when verbose=False."""
        silent_logger.error("should not appear")
        captured = capsys.readouterr()
        assert captured.err == ""


# =============================================================================
# TestLoggerTiming
# =============================================================================


class TestLoggerTiming:
    """Tests for timing() method."""

    def test_timing_prints_message(
        self, logger: Logger, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Message appears in output."""
        logger.timing("timing message")
        captured = capsys.readouterr()
        assert "timing message" in captured.out

    def test_timing_uses_magenta_color(
        self, logger: Logger, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Uses MAGENTA color code."""
        logger.timing("test")
        captured = capsys.readouterr()
        assert Logger.MAGENTA in captured.out

    def test_timing_silent_when_not_verbose(
        self, silent_logger: Logger, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """No output when verbose=False."""
        silent_logger.timing("should not appear")
        captured = capsys.readouterr()
        assert captured.out == ""


# =============================================================================
# TestLoggerHeader
# =============================================================================


class TestLoggerHeader:
    """Tests for header() method."""

    def test_header_prints_separator_and_message(
        self, logger: Logger, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Contains separator lines and message."""
        logger.header("Header Text")
        captured = capsys.readouterr()
        assert "Header Text" in captured.out
        assert "=" in captured.out  # Default separator

    def test_header_uses_custom_char(
        self, logger: Logger, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Uses specified separator character."""
        logger.header("Test", char="-")
        captured = capsys.readouterr()
        assert "-" in captured.out
        # Should contain multiple dashes (separator line)
        assert captured.out.count("-") >= 10

    def test_header_uses_custom_width(
        self, logger: Logger, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Uses specified width for separators."""
        logger.header("Test", char="*", width=20)
        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")
        # First line should be 20 asterisks
        assert lines[0] == "*" * 20

    def test_header_default_equals_char(
        self, logger: Logger, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Default char is '='."""
        logger.header("Test")
        captured = capsys.readouterr()
        assert "============" in captured.out

    def test_header_default_width_60(
        self, logger: Logger, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Default width is 60."""
        logger.header("Test")
        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")
        assert len(lines[0]) == 60

    def test_header_silent_when_not_verbose(
        self, silent_logger: Logger, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """No output when verbose=False."""
        silent_logger.header("Should not appear")
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_header_has_three_lines(
        self, logger: Logger, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Header outputs separator, message, separator."""
        logger.header("Message")
        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")
        assert len(lines) == 3
        assert lines[1] == "Message"


# =============================================================================
# TestFormatDuration
# =============================================================================


class TestFormatDuration:
    """Tests for format_duration() function."""

    def test_seconds_under_60(self) -> None:
        """'5.2 seconds' for 5.2."""
        result = format_duration(5.2)
        assert result == "5.2 seconds"

    def test_exactly_60_seconds(self) -> None:
        """'1.0 minutes' for 60.0."""
        result = format_duration(60.0)
        assert result == "1.0 minutes"

    def test_over_60_uses_minutes(self) -> None:
        """Uses minutes format for values >= 60."""
        result = format_duration(90.0)
        assert result == "1.5 minutes"

    def test_zero_seconds(self) -> None:
        """'0.0 seconds' for 0.0."""
        result = format_duration(0.0)
        assert result == "0.0 seconds"

    def test_fractional_seconds(self) -> None:
        """Handles fractional seconds."""
        result = format_duration(0.5)
        assert result == "0.5 seconds"

    def test_large_minutes(self) -> None:
        """Handles large values in minutes."""
        result = format_duration(3600.0)  # 1 hour
        assert result == "60.0 minutes"

    def test_precision_one_decimal(self) -> None:
        """Output has one decimal place."""
        result = format_duration(12.345)
        assert result == "12.3 seconds"

    def test_minutes_precision(self) -> None:
        """Minutes have one decimal place."""
        result = format_duration(125.5)  # 2.09 minutes
        assert result == "2.1 minutes"

    def test_just_under_60(self) -> None:
        """59.9 seconds stays in seconds."""
        result = format_duration(59.9)
        assert result == "59.9 seconds"


# =============================================================================
# Edge Cases
# =============================================================================


class TestLoggerEdgeCases:
    """Edge case tests for Logger."""

    def test_empty_message(self, logger: Logger, capsys: pytest.CaptureFixture[str]) -> None:
        """Empty string message still outputs timestamp."""
        logger.info("")
        captured = capsys.readouterr()
        # Should still have timestamp
        assert re.search(r"\[\d{2}:\d{2}:\d{2}\]", captured.out) is not None

    def test_long_message(self, logger: Logger, capsys: pytest.CaptureFixture[str]) -> None:
        """Long messages are not truncated."""
        long_msg = "x" * 1000
        logger.info(long_msg)
        captured = capsys.readouterr()
        assert long_msg in captured.out

    def test_unicode_message(self, logger: Logger, capsys: pytest.CaptureFixture[str]) -> None:
        """Unicode characters handled correctly."""
        logger.info("Unicode: \u2714 \u2717 \U0001f600")
        captured = capsys.readouterr()
        assert "\u2714" in captured.out
        assert "\U0001f600" in captured.out

    def test_newlines_in_message(self, logger: Logger, capsys: pytest.CaptureFixture[str]) -> None:
        """Messages with newlines are preserved."""
        logger.info("Line 1\nLine 2")
        captured = capsys.readouterr()
        assert "Line 1\nLine 2" in captured.out

    def test_special_characters(self, logger: Logger, capsys: pytest.CaptureFixture[str]) -> None:
        """Special characters are not escaped."""
        logger.info("Special: <>&\"'")
        captured = capsys.readouterr()
        assert "<>&\"'" in captured.out

    def test_multiple_calls_different_timestamps(
        self, logger: Logger, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Each call gets current timestamp (at least same format)."""
        logger.info("first")
        captured1 = capsys.readouterr()
        logger.info("second")
        captured2 = capsys.readouterr()

        # Both should have timestamp format
        assert re.search(r"\[\d{2}:\d{2}:\d{2}\]", captured1.out)
        assert re.search(r"\[\d{2}:\d{2}:\d{2}\]", captured2.out)


class TestFormatDurationEdgeCases:
    """Edge case tests for format_duration()."""

    def test_very_small_value(self) -> None:
        """Very small values format correctly."""
        result = format_duration(0.001)
        assert result == "0.0 seconds"

    def test_negative_value(self) -> None:
        """Negative values are formatted (no validation)."""
        result = format_duration(-5.0)
        assert result == "-5.0 seconds"

    def test_integer_input(self) -> None:
        """Integer input is handled."""
        result = format_duration(30)
        assert result == "30.0 seconds"

    def test_boundary_59_point_99(self) -> None:
        """59.99 rounds and stays in seconds."""
        result = format_duration(59.99)
        # 59.99 -> "60.0 seconds" due to rounding, OR might stay under
        # Actual behavior: 59.99 < 60, so seconds
        assert "seconds" in result
