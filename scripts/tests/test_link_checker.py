"""Tests for link_checker module."""

import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from little_loops.link_checker import (
    LinkCheckResult,
    LinkResult,
    check_markdown_links,
    check_url,
    extract_links_from_markdown,
    format_result_json,
    format_result_markdown,
    format_result_text,
    is_internal_reference,
    load_ignore_patterns,
    should_ignore_url,
)


class TestExtractLinks:
    """Tests for extract_links_from_markdown function."""

    def test_extract_markdown_links(self, tmp_path: Path) -> None:
        """Extract standard markdown links [text](url)."""
        content = """
# Test Document

This is a [link to Google](https://www.google.com) and a [link to GitHub](https://github.com).
"""
        links = extract_links_from_markdown(content, "test.md")
        assert len(links) == 2
        assert ("https://www.google.com", "link to Google", 4) in links
        assert ("https://github.com", "link to GitHub", 4) in links

    def test_extract_bare_urls(self, tmp_path: Path) -> None:
        """Extract bare URLs in text."""
        content = """
Visit https://www.example.com for more info.
Also check http://localhost:8080
"""
        links = extract_links_from_markdown(content, "test.md")
        assert len(links) == 2
        urls = [url for url, _, _ in links]
        assert "https://www.example.com" in urls
        assert "http://localhost:8080" in urls

    def test_extract_links_with_punctuation(self, tmp_path: Path) -> None:
        """Extract links with trailing punctuation."""
        content = """
Check out https://example.com, and also https://github.com.
"""
        links = extract_links_from_markdown(content, "test.md")
        assert len(links) == 2
        # Trailing comma should be stripped
        assert ("https://example.com", None, 2) in links

    def test_extract_multiple_links_same_line(self, tmp_path: Path) -> None:
        """Extract multiple links from the same line."""
        content = "[one](https://one.com) and [two](https://two.com)\n"
        links = extract_links_from_markdown(content, "test.md")
        assert len(links) == 2
        assert ("https://one.com", "one", 1) in links
        assert ("https://two.com", "two", 1) in links

    def test_extract_no_links(self, tmp_path: Path) -> None:
        """Handle content with no links."""
        content = "# Just a header\n\nSome text without links.\n"
        links = extract_links_from_markdown(content, "test.md")
        assert len(links) == 0

    def test_extract_internal_references(self, tmp_path: Path) -> None:
        """Extract internal references."""
        content = """
See [internal](./other.md) or [top](#readme).
Also check [parent](../README.md).
"""
        links = extract_links_from_markdown(content, "test.md")
        assert len(links) == 3
        urls = [url for url, _, _ in links]
        assert "./other.md" in urls
        assert "#readme" in urls
        assert "../README.md" in urls


class TestIsInternalReference:
    """Tests for is_internal_reference function."""

    def test_hash_references(self) -> None:
        """Hash references are internal."""
        assert is_internal_reference("#section") is True
        assert is_internal_reference("#readme") is True

    def test_relative_path_references(self) -> None:
        """Relative path references are internal."""
        assert is_internal_reference("./other.md") is True
        assert is_internal_reference("../README.md") is True
        assert is_internal_reference("./docs/api.md") is True

    def test_markdown_files(self) -> None:
        """Markdown file references are internal."""
        assert is_internal_reference("README.md") is True
        assert is_internal_reference("docs/ARCHITECTURE.md") is True

    def test_http_urls(self) -> None:
        """HTTP URLs are not internal."""
        assert is_internal_reference("https://example.com") is False
        assert is_internal_reference("http://localhost:8080") is False


class TestShouldIgnoreUrl:
    """Tests for should_ignore_url function."""

    def test_ignore_localhost(self) -> None:
        """Ignore localhost URLs."""
        patterns = [r"^http://localhost", r"^https://localhost"]
        assert should_ignore_url("http://localhost:8080", patterns) is True
        assert should_ignore_url("https://localhost/api", patterns) is True

    def test_ignore_ip_addresses(self) -> None:
        """Ignore 127.0.0.1 URLs."""
        patterns = [r"^http://127\.0\.0\.1", r"^https://127\.0\.0\.1"]
        assert should_ignore_url("http://127.0.0.1:8000", patterns) is True

    def test_ignore_custom_pattern(self) -> None:
        """Ignore custom patterns."""
        patterns = [r"^https://github.com/.*"]
        assert should_ignore_url("https://github.com/user/repo", patterns) is True
        assert should_ignore_url("https://gitlab.com/user/repo", patterns) is False

    def test_no_ignore_when_no_match(self) -> None:
        """Don't ignore when pattern doesn't match."""
        patterns = [r"^http://localhost"]
        assert should_ignore_url("https://example.com", patterns) is False

    def test_empty_patterns(self) -> None:
        """Handle empty patterns list."""
        assert should_ignore_url("http://localhost:8080", []) is False


class TestCheckUrl:
    """Tests for check_url function."""

    @patch("urllib.request.urlopen")
    def test_valid_url(self, mock_urlopen: Mock) -> None:
        """Valid URL returns True."""
        mock_response = Mock()
        mock_response.status = 200
        mock_urlopen.return_value.__enter__.return_value = mock_response

        is_valid, error = check_url("https://example.com")
        assert is_valid is True
        assert error is None

    @patch("urllib.request.urlopen")
    def test_redirect_url(self, mock_urlopen: Mock) -> None:
        """Redirect URLs (3xx) are considered valid."""
        mock_response = Mock()
        mock_response.status = 301
        mock_urlopen.return_value.__enter__.return_value = mock_response

        is_valid, error = check_url("https://example.com")
        assert is_valid is True
        assert error is None

    @patch("urllib.request.urlopen")
    def test_404_error(self, mock_urlopen: Mock) -> None:
        """404 errors are detected."""
        import urllib.error

        mock_urlopen.side_effect = urllib.error.HTTPError(
            "https://example.com", 404, "Not Found", {}, None
        )

        is_valid, error = check_url("https://example.com")
        assert is_valid is False
        assert "HTTP 404" in error

    @patch("urllib.request.urlopen")
    def test_connection_error(self, mock_urlopen: Mock) -> None:
        """Connection errors are detected."""
        import urllib.error

        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")

        is_valid, error = check_url("https://example.com")
        assert is_valid is False
        assert "Connection error" in error

    @patch("urllib.request.urlopen")
    def test_timeout_error(self, mock_urlopen: Mock) -> None:
        """Timeout errors are detected."""
        mock_urlopen.side_effect = TimeoutError()

        is_valid, error = check_url("https://example.com", timeout=1)
        assert is_valid is False
        assert error == "Timeout"


class TestCheckMarkdownLinks:
    """Integration tests for check_markdown_links function."""

    def test_check_with_valid_links(self, tmp_path: Path) -> None:
        """All links are valid (mocked)."""
        # Create test markdown file
        test_file = tmp_path / "test.md"
        test_file.write_text(
            """
# Test

[Link](https://example.com)
"""
        )

        with patch("little_loops.link_checker.check_url") as mock_check:
            mock_check.return_value = (True, None)

            result = check_markdown_links(tmp_path, [], timeout=10)

            assert result.total_links == 1
            assert result.valid_links == 1
            assert result.broken_links == 0
            assert result.has_errors is False

    def test_check_with_broken_link(self, tmp_path: Path) -> None:
        """Broken links are detected."""
        test_file = tmp_path / "test.md"
        test_file.write_text("[Link](https://invalid.example.com)\n")

        with patch("little_loops.link_checker.check_url") as mock_check:
            mock_check.return_value = (False, "HTTP 404")

            result = check_markdown_links(tmp_path, [], timeout=10)

            assert result.total_links == 1
            assert result.broken_links == 1
            assert result.has_errors is True

    def test_check_with_internal_links(self, tmp_path: Path) -> None:
        """Internal references are tracked separately."""
        test_file = tmp_path / "test.md"
        test_file.write_text(
            """
[Internal](./other.md)
[Anchor](#section)
"""
        )

        result = check_markdown_links(tmp_path, [], timeout=10)

        assert result.internal_links == 2
        assert result.valid_links == 0
        assert result.broken_links == 0

    def test_check_with_ignored_links(self, tmp_path: Path) -> None:
        """Ignored patterns work correctly."""
        test_file = tmp_path / "test.md"
        test_file.write_text("[Local](http://localhost:8080)\n")

        result = check_markdown_links(
            tmp_path, [r"^http://localhost"], timeout=10
        )

        assert result.ignored_links == 1
        assert result.valid_links == 0
        assert result.broken_links == 0

    def test_check_multiple_files(self, tmp_path: Path) -> None:
        """Check multiple markdown files."""
        (tmp_path / "test1.md").write_text("[Link1](https://one.com)\n")
        (tmp_path / "test2.md").write_text("[Link2](https://two.com)\n")

        with patch("little_loops.link_checker.check_url") as mock_check:
            mock_check.return_value = (True, None)

            result = check_markdown_links(tmp_path, [], timeout=10)

            assert result.total_links == 2
            assert result.valid_links == 2

    def test_check_recursive_subdirectories(self, tmp_path: Path) -> None:
        """Check files in subdirectories."""
        subdir = tmp_path / "docs"
        subdir.mkdir()
        (subdir / "api.md").write_text("[API](https://api.example.com)\n")

        with patch("little_loops.link_checker.check_url") as mock_check:
            mock_check.return_value = (True, None)

            result = check_markdown_links(tmp_path, [], timeout=10)

            assert result.total_links == 1
            assert result.valid_links == 1

    def test_check_with_no_markdown_files(self, tmp_path: Path) -> None:
        """Handle directory with no markdown files."""
        result = check_markdown_links(tmp_path, [], timeout=10)

        assert result.total_links == 0
        assert result.valid_links == 0


class TestLoadIgnorePatterns:
    """Tests for load_ignore_patterns function."""

    def test_load_from_config_file(self, tmp_path: Path) -> None:
        """Load patterns from .mlc.config.json."""
        config_file = tmp_path / ".mlc.config.json"
        config_file.write_text(
            json.dumps(
                {
                    "ignorePatterns": [
                        {"pattern": "^http://localhost"},
                        {"pattern": "^https://private.example.com"},
                    ]
                }
            )
        )

        patterns = load_ignore_patterns(tmp_path)

        assert len(patterns) > 2  # Includes defaults
        assert any("localhost" in p for p in patterns)
        assert any("private.example.com" in p for p in patterns)

    def test_no_config_file(self, tmp_path: Path) -> None:
        """Return defaults when no config file exists."""
        patterns = load_ignore_patterns(tmp_path)

        # Should have default patterns
        assert len(patterns) > 0
        assert any("localhost" in p for p in patterns)

    def test_invalid_json(self, tmp_path: Path) -> None:
        """Handle invalid JSON gracefully."""
        config_file = tmp_path / ".mlc.config.json"
        config_file.write_text("invalid json {{{")

        patterns = load_ignore_patterns(tmp_path)

        # Should fall back to defaults
        assert len(patterns) > 0


class TestFormatters:
    """Tests for output formatters."""

    def test_format_result_text_no_errors(self) -> None:
        """Text format with no errors."""
        result = LinkCheckResult(
            total_links=10,
            valid_links=8,
            broken_links=0,
            ignored_links=2,
            internal_links=0,
            results=[],
        )

        output = format_result_text(result)

        assert "All 10 link(s) valid!" in output
        assert "2 ignored" in output

    def test_format_result_text_with_errors(self) -> None:
        """Text format with broken links."""
        result = LinkCheckResult(
            total_links=2,
            valid_links=1,
            broken_links=1,
            ignored_links=0,
            internal_links=0,
            results=[
                LinkResult(
                    url="https://broken.com",
                    file="test.md",
                    line=5,
                    status="broken",
                    error="HTTP 404",
                    link_text="Broken Link",
                )
            ],
        )

        output = format_result_text(result)

        assert "Found 1 broken link" in output
        assert "https://broken.com" in output
        assert "test.md:5" in output
        assert "HTTP 404" in output

    def test_format_result_json(self) -> None:
        """JSON format output."""
        result = LinkCheckResult(
            total_links=5,
            valid_links=3,
            broken_links=1,
            ignored_links=1,
            internal_links=0,
            results=[
                LinkResult(
                    url="https://test.com",
                    file="test.md",
                    line=1,
                    status="valid",
                    link_text="Test",
                )
            ],
        )

        output = format_result_json(result)
        data = json.loads(output)

        assert data["total_links"] == 5
        assert data["valid_links"] == 3
        assert data["broken_links"] == 1
        assert data["has_errors"] is True
        assert len(data["results"]) == 1
        assert data["results"][0]["url"] == "https://test.com"

    def test_format_result_markdown_no_errors(self) -> None:
        """Markdown format with no errors."""
        result = LinkCheckResult(
            total_links=10,
            valid_links=8,
            broken_links=0,
            ignored_links=2,
            internal_links=0,
            results=[],
        )

        output = format_result_markdown(result)

        assert "# Documentation Link Check" in output
        assert "## Summary" in output
        assert "**Total links**: 10" in output
        assert "## ✅ All Links Valid" in output

    def test_format_result_markdown_with_errors(self) -> None:
        """Markdown format with broken links."""
        result = LinkCheckResult(
            total_links=2,
            valid_links=1,
            broken_links=1,
            ignored_links=0,
            internal_links=0,
            results=[
                LinkResult(
                    url="https://broken.com",
                    file="test.md",
                    line=5,
                    status="broken",
                    error="HTTP 404",
                )
            ],
        )

        output = format_result_markdown(result)

        assert "## ❌ Broken Links" in output
        assert "| URL | File | Line | Error |" in output
        assert "broken.com" in output
        assert "test.md" in output
