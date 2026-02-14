"""Tests for little_loops.cli_args module.

Tests cover:
- Argument addition functions
- parse_issue_ids() utility function
- Help text generation
"""

import argparse
from pathlib import Path

from little_loops.cli_args import (
    VALID_ISSUE_TYPES,
    add_common_auto_args,
    add_common_parallel_args,
    add_config_arg,
    add_dry_run_arg,
    add_max_workers_arg,
    add_resume_arg,
    add_skip_arg,
    add_timeout_arg,
    add_type_arg,
    parse_issue_ids,
    parse_issue_types,
)


class TestParseIssueIds:
    """Tests for parse_issue_ids() function."""

    def test_none_returns_none(self) -> None:
        """None input returns None."""
        result = parse_issue_ids(None)
        assert result is None

    def test_single_issue(self) -> None:
        """Single issue ID is uppercased."""
        result = parse_issue_ids("bug-001")
        assert result == {"BUG-001"}

    def test_multiple_issues(self) -> None:
        """Multiple comma-separated issues are uppercased and split."""
        result = parse_issue_ids("BUG-001,feat-002,ENH-003")
        assert result == {"BUG-001", "FEAT-002", "ENH-003"}

    def test_whitespace_handling(self) -> None:
        """Whitespace around IDs is stripped."""
        result = parse_issue_ids(" BUG-001 , feat-002 , ENH-003 ")
        assert result == {"BUG-001", "FEAT-002", "ENH-003"}

    def test_empty_string(self) -> None:
        """Empty string returns set with empty string (matches original behavior).

        This preserves the original behavior where "".split(",") returns [""],
        which after strip/upper becomes {""}. In practice, this case is handled
        by checking `if skip_ids:` before using the result.
        """
        result = parse_issue_ids("")
        assert result == {""}


class TestParseIssueTypes:
    """Tests for parse_issue_types() function."""

    def test_none_returns_none(self) -> None:
        """None input returns None."""
        result = parse_issue_types(None)
        assert result is None

    def test_single_type(self) -> None:
        """Single type is uppercased."""
        result = parse_issue_types("bug")
        assert result == {"BUG"}

    def test_multiple_types(self) -> None:
        """Multiple comma-separated types are uppercased and split."""
        result = parse_issue_types("BUG,enh")
        assert result == {"BUG", "ENH"}

    def test_all_types(self) -> None:
        """All valid types are accepted."""
        result = parse_issue_types("BUG,FEAT,ENH")
        assert result == {"BUG", "FEAT", "ENH"}

    def test_whitespace_handling(self) -> None:
        """Whitespace around types is stripped."""
        result = parse_issue_types(" BUG , ENH ")
        assert result == {"BUG", "ENH"}

    def test_invalid_type_exits(self) -> None:
        """Invalid type causes SystemExit with code 2."""
        import pytest

        with pytest.raises(SystemExit) as exc_info:
            parse_issue_types("INVALID")
        assert exc_info.value.code == 2

    def test_mixed_valid_invalid_exits(self) -> None:
        """Mix of valid and invalid types causes SystemExit."""
        import pytest

        with pytest.raises(SystemExit) as exc_info:
            parse_issue_types("BUG,INVALID")
        assert exc_info.value.code == 2


class TestValidIssueTypes:
    """Tests for VALID_ISSUE_TYPES constant."""

    def test_contains_expected_types(self) -> None:
        """Contains BUG, FEAT, and ENH."""
        assert VALID_ISSUE_TYPES == {"BUG", "FEAT", "ENH"}


class TestAddTypeArg:
    """Tests for add_type_arg() function."""

    def test_adds_type_argument(self) -> None:
        """Adds --type argument that accepts string."""
        parser = argparse.ArgumentParser()
        add_type_arg(parser)
        args = parser.parse_args(["--type", "BUG"])
        assert args.type == "BUG"

    def test_default_is_none(self) -> None:
        """Default value is None."""
        parser = argparse.ArgumentParser()
        add_type_arg(parser)
        args = parser.parse_args([])
        assert args.type is None

    def test_accepts_multiple_types(self) -> None:
        """Accepts comma-separated types as raw string."""
        parser = argparse.ArgumentParser()
        add_type_arg(parser)
        args = parser.parse_args(["--type", "BUG,ENH"])
        assert args.type == "BUG,ENH"


class TestAddDryRunArg:
    """Tests for add_dry_run_arg() function."""

    def test_adds_dry_run_flag(self) -> None:
        """Adds --dry-run and -n flags as store_true."""
        parser = argparse.ArgumentParser()
        add_dry_run_arg(parser)
        args = parser.parse_args(["--dry-run"])
        assert args.dry_run is True

    def test_short_flag(self) -> None:
        """Short -n flag works."""
        parser = argparse.ArgumentParser()
        add_dry_run_arg(parser)
        args = parser.parse_args(["-n"])
        assert args.dry_run is True

    def test_default_is_false(self) -> None:
        """Default value is False."""
        parser = argparse.ArgumentParser()
        add_dry_run_arg(parser)
        args = parser.parse_args([])
        assert args.dry_run is False


class TestAddResumeArg:
    """Tests for add_resume_arg() function."""

    def test_adds_resume_flag(self) -> None:
        """Adds --resume and -r flags as store_true."""
        parser = argparse.ArgumentParser()
        add_resume_arg(parser)
        args = parser.parse_args(["--resume"])
        assert args.resume is True

    def test_short_flag(self) -> None:
        """Short -r flag works."""
        parser = argparse.ArgumentParser()
        add_resume_arg(parser)
        args = parser.parse_args(["-r"])
        assert args.resume is True


class TestAddConfigArg:
    """Tests for add_config_arg() function."""

    def test_adds_config_path(self) -> None:
        """Adds --config argument that parses as Path."""
        parser = argparse.ArgumentParser()
        add_config_arg(parser)
        args = parser.parse_args(["--config", "/some/path"])
        assert args.config == Path("/some/path")

    def test_default_is_none(self) -> None:
        """Default value is None."""
        parser = argparse.ArgumentParser()
        add_config_arg(parser)
        args = parser.parse_args([])
        assert args.config is None


class TestAddMaxWorkersArg:
    """Tests for add_max_workers_arg() function."""

    def test_with_default(self) -> None:
        """Adds argument with specified default."""
        parser = argparse.ArgumentParser()
        add_max_workers_arg(parser, default=4)
        args = parser.parse_args([])
        assert args.max_workers == 4

    def test_without_default(self) -> None:
        """Adds argument with None default."""
        parser = argparse.ArgumentParser()
        add_max_workers_arg(parser)
        args = parser.parse_args([])
        assert args.max_workers is None

    def test_accepts_integer(self) -> None:
        """Accepts integer value."""
        parser = argparse.ArgumentParser()
        add_max_workers_arg(parser)
        args = parser.parse_args(["--max-workers", "8"])
        assert args.max_workers == 8

    def test_short_flag(self) -> None:
        """Short -w flag works."""
        parser = argparse.ArgumentParser()
        add_max_workers_arg(parser)
        args = parser.parse_args(["-w", "3"])
        assert args.max_workers == 3


class TestAddTimeoutArg:
    """Tests for add_timeout_arg() function."""

    def test_with_default(self) -> None:
        """Adds argument with specified default."""
        parser = argparse.ArgumentParser()
        add_timeout_arg(parser, default=3600)
        args = parser.parse_args([])
        assert args.timeout == 3600

    def test_without_default(self) -> None:
        """Adds argument with None default."""
        parser = argparse.ArgumentParser()
        add_timeout_arg(parser)
        args = parser.parse_args([])
        assert args.timeout is None

    def test_accepts_integer(self) -> None:
        """Accepts integer value."""
        parser = argparse.ArgumentParser()
        add_timeout_arg(parser)
        args = parser.parse_args(["--timeout", "1800"])
        assert args.timeout == 1800


class TestAddSkipArg:
    """Tests for add_skip_arg() function."""

    def test_default_help_text(self) -> None:
        """Uses default help text when not specified."""
        parser = argparse.ArgumentParser()
        add_skip_arg(parser)
        help_text = parser.format_help()
        assert "Comma-separated list of issue IDs to skip" in help_text

    def test_custom_help_text(self) -> None:
        """Uses custom help text when provided."""
        parser = argparse.ArgumentParser()
        add_skip_arg(parser, help_text="Custom help message")
        help_text = parser.format_help()
        assert "Custom help message" in help_text


class TestAddCommonAutoArgs:
    """Tests for add_common_auto_args() function."""

    def test_adds_all_expected_arguments(self) -> None:
        """Adds resume, dry-run, max-issues, only, skip, type, config."""
        parser = argparse.ArgumentParser()
        add_common_auto_args(parser)
        args = parser.parse_args(
            [
                "--resume",
                "--dry-run",
                "--max-issues",
                "5",
                "--only",
                "BUG-001",
                "--skip",
                "BUG-002",
                "--type",
                "BUG",
                "--config",
                "/path",
            ]
        )
        assert args.resume is True
        assert args.dry_run is True
        assert args.max_issues == 5
        assert args.only == "BUG-001"
        assert args.skip == "BUG-002"
        assert args.type == "BUG"
        assert args.config is not None


class TestAddCommonParallelArgs:
    """Tests for add_common_parallel_args() function."""

    def test_adds_all_expected_arguments(self) -> None:
        """Adds dry-run, resume, max-workers, timeout, quiet, only, skip, type, config."""
        parser = argparse.ArgumentParser()
        add_common_parallel_args(parser)
        args = parser.parse_args(
            [
                "--dry-run",
                "--resume",
                "--max-workers",
                "3",
                "--timeout",
                "1800",
                "--quiet",
                "--only",
                "BUG-001",
                "--skip",
                "BUG-002",
                "--type",
                "ENH",
                "--config",
                "/path",
            ]
        )
        assert args.dry_run is True
        assert args.resume is True
        assert args.max_workers == 3
        assert args.timeout == 1800
        assert args.quiet is True
        assert args.only == "BUG-001"
        assert args.skip == "BUG-002"
        assert args.type == "ENH"
        assert args.config is not None
