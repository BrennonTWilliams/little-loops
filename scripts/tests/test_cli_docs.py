"""Tests for cli/docs.py - ll-verify-docs and ll-check-links CLI entry points."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from little_loops.cli.docs import main_check_links, main_verify_docs


class TestMainVerifyDocs:
    """Tests for main_verify_docs entry point."""

    def _make_verify_result(self, all_match: bool = True) -> MagicMock:
        """Create a mock VerificationResult."""
        result = MagicMock()
        result.all_match = all_match
        return result

    def test_text_output_default(self) -> None:
        """Default format is text, returns 0 when all match."""
        mock_result = self._make_verify_result(all_match=True)

        with (
            patch("sys.argv", ["ll-verify-docs"]),
            patch(
                "little_loops.doc_counts.verify_documentation",
                return_value=mock_result,
            ),
            patch("little_loops.doc_counts.format_result_text", return_value="All OK"),
            patch("builtins.print") as mock_print,
        ):
            result = main_verify_docs()

        assert result == 0
        mock_print.assert_any_call("All OK")

    def test_json_output_flag(self) -> None:
        """--json flag uses JSON formatter."""
        mock_result = self._make_verify_result(all_match=True)

        with (
            patch("sys.argv", ["ll-verify-docs", "--json"]),
            patch(
                "little_loops.doc_counts.verify_documentation",
                return_value=mock_result,
            ),
            patch(
                "little_loops.doc_counts.format_result_json",
                return_value='{"ok": true}',
            ),
            patch("builtins.print") as mock_print,
        ):
            result = main_verify_docs()

        assert result == 0
        mock_print.assert_any_call('{"ok": true}')

    def test_json_format_option(self) -> None:
        """--format json uses JSON formatter."""
        mock_result = self._make_verify_result(all_match=True)

        with (
            patch("sys.argv", ["ll-verify-docs", "--format", "json"]),
            patch(
                "little_loops.doc_counts.verify_documentation",
                return_value=mock_result,
            ),
            patch(
                "little_loops.doc_counts.format_result_json",
                return_value='{"ok": true}',
            ),
            patch("builtins.print") as mock_print,
        ):
            main_verify_docs()

        mock_print.assert_any_call('{"ok": true}')

    def test_markdown_format_option(self) -> None:
        """--format markdown uses markdown formatter."""
        mock_result = self._make_verify_result(all_match=True)

        with (
            patch("sys.argv", ["ll-verify-docs", "--format", "markdown"]),
            patch(
                "little_loops.doc_counts.verify_documentation",
                return_value=mock_result,
            ),
            patch(
                "little_loops.doc_counts.format_result_markdown",
                return_value="# OK",
            ),
            patch("builtins.print") as mock_print,
        ):
            main_verify_docs()

        mock_print.assert_any_call("# OK")

    def test_mismatch_returns_1(self) -> None:
        """Returns 1 when mismatches found."""
        mock_result = self._make_verify_result(all_match=False)

        with (
            patch("sys.argv", ["ll-verify-docs"]),
            patch(
                "little_loops.doc_counts.verify_documentation",
                return_value=mock_result,
            ),
            patch(
                "little_loops.doc_counts.format_result_text",
                return_value="MISMATCH",
            ),
            patch("builtins.print"),
        ):
            result = main_verify_docs()

        assert result == 1

    def test_fix_flag_with_mismatches(self) -> None:
        """--fix calls fix_counts when mismatches found."""
        mock_result = self._make_verify_result(all_match=False)
        mock_fix_result = MagicMock()
        mock_fix_result.fixed_count = 3
        mock_fix_result.files_modified = ["file1.md", "file2.md"]

        with (
            patch("sys.argv", ["ll-verify-docs", "--fix"]),
            patch(
                "little_loops.doc_counts.verify_documentation",
                return_value=mock_result,
            ),
            patch(
                "little_loops.doc_counts.format_result_text",
                return_value="MISMATCH",
            ),
            patch(
                "little_loops.doc_counts.fix_counts",
                return_value=mock_fix_result,
            ) as mock_fix,
            patch("builtins.print"),
        ):
            result = main_verify_docs()

        assert result == 1
        mock_fix.assert_called_once()

    def test_fix_flag_without_mismatches(self) -> None:
        """--fix does not call fix_counts when all match."""
        mock_result = self._make_verify_result(all_match=True)

        with (
            patch("sys.argv", ["ll-verify-docs", "--fix"]),
            patch(
                "little_loops.doc_counts.verify_documentation",
                return_value=mock_result,
            ),
            patch(
                "little_loops.doc_counts.format_result_text",
                return_value="All OK",
            ),
            patch(
                "little_loops.doc_counts.fix_counts",
            ) as mock_fix,
            patch("builtins.print"),
        ):
            main_verify_docs()

        mock_fix.assert_not_called()

    def test_custom_directory(self, tmp_path: Path) -> None:
        """--directory uses provided path."""

        mock_result = self._make_verify_result(all_match=True)

        with (
            patch("sys.argv", ["ll-verify-docs", "--directory", str(tmp_path)]),
            patch(
                "little_loops.doc_counts.verify_documentation",
                return_value=mock_result,
            ) as mock_verify,
            patch("little_loops.doc_counts.format_result_text", return_value="OK"),
            patch("builtins.print"),
        ):
            main_verify_docs()

        mock_verify.assert_called_once_with(Path(str(tmp_path)))


class TestMainCheckLinks:
    """Tests for main_check_links entry point."""

    def _make_link_result(self, has_errors: bool = False) -> MagicMock:
        """Create a mock LinkCheckResult."""
        result = MagicMock()
        result.has_errors = has_errors
        return result

    def test_text_output_default_no_errors(self) -> None:
        """Default format is text, returns 0 when no errors."""
        mock_result = self._make_link_result(has_errors=False)

        with (
            patch("sys.argv", ["ll-check-links"]),
            patch("little_loops.link_checker.load_ignore_patterns", return_value=[]),
            patch(
                "little_loops.link_checker.check_markdown_links",
                return_value=mock_result,
            ),
            patch(
                "little_loops.link_checker.format_result_text",
                return_value="All links OK",
            ),
            patch("builtins.print") as mock_print,
        ):
            result = main_check_links()

        assert result == 0
        mock_print.assert_any_call("All links OK")

    def test_errors_returns_1(self) -> None:
        """Returns 1 when broken links found."""
        mock_result = self._make_link_result(has_errors=True)

        with (
            patch("sys.argv", ["ll-check-links"]),
            patch("little_loops.link_checker.load_ignore_patterns", return_value=[]),
            patch(
                "little_loops.link_checker.check_markdown_links",
                return_value=mock_result,
            ),
            patch(
                "little_loops.link_checker.format_result_text",
                return_value="ERRORS",
            ),
            patch("builtins.print"),
        ):
            result = main_check_links()

        assert result == 1

    def test_json_output_flag(self) -> None:
        """--json flag uses JSON formatter."""
        mock_result = self._make_link_result(has_errors=False)

        with (
            patch("sys.argv", ["ll-check-links", "--json"]),
            patch("little_loops.link_checker.load_ignore_patterns", return_value=[]),
            patch(
                "little_loops.link_checker.check_markdown_links",
                return_value=mock_result,
            ),
            patch("little_loops.link_checker.format_result_json", return_value="{}"),
            patch("builtins.print") as mock_print,
        ):
            main_check_links()

        mock_print.assert_any_call("{}")

    def test_markdown_format_option(self) -> None:
        """--format markdown uses markdown formatter."""
        mock_result = self._make_link_result(has_errors=False)

        with (
            patch("sys.argv", ["ll-check-links", "--format", "markdown"]),
            patch("little_loops.link_checker.load_ignore_patterns", return_value=[]),
            patch(
                "little_loops.link_checker.check_markdown_links",
                return_value=mock_result,
            ),
            patch(
                "little_loops.link_checker.format_result_markdown",
                return_value="# OK",
            ),
            patch("builtins.print") as mock_print,
        ):
            main_check_links()

        mock_print.assert_any_call("# OK")

    def test_ignore_patterns_combined(self) -> None:
        """CLI --ignore patterns extend config-loaded patterns."""
        mock_result = self._make_link_result(has_errors=False)

        with (
            patch(
                "sys.argv",
                ["ll-check-links", "--ignore", "http://localhost.*"],
            ),
            patch(
                "little_loops.link_checker.load_ignore_patterns",
                return_value=["http://example.com"],
            ),
            patch(
                "little_loops.link_checker.check_markdown_links",
                return_value=mock_result,
            ) as mock_check,
            patch("little_loops.link_checker.format_result_text", return_value="OK"),
            patch("builtins.print"),
        ):
            main_check_links()

        # Verify combined patterns passed to check function
        call_args = mock_check.call_args[0]
        ignore_patterns = call_args[1]
        assert "http://example.com" in ignore_patterns
        assert "http://localhost.*" in ignore_patterns

    def test_custom_timeout_and_workers(self) -> None:
        """--timeout and --workers are passed to check function."""
        mock_result = self._make_link_result(has_errors=False)

        with (
            patch(
                "sys.argv",
                ["ll-check-links", "--timeout", "30", "--workers", "5"],
            ),
            patch("little_loops.link_checker.load_ignore_patterns", return_value=[]),
            patch(
                "little_loops.link_checker.check_markdown_links",
                return_value=mock_result,
            ) as mock_check,
            patch("little_loops.link_checker.format_result_text", return_value="OK"),
            patch("builtins.print"),
        ):
            main_check_links()

        call_args = mock_check.call_args[0]
        assert call_args[2] == 30  # timeout
        assert call_args[4] == 5  # workers
