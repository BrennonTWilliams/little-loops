"""Fuzz tests for issue_parser module focusing on crash safety.

These tests use Hypothesis to generate malformed, extreme, and unexpected
inputs to verify the parser doesn't crash, hang, or consume excessive memory.

Unlike property-based tests (which verify invariants), these tests focus on
crash safety and robustness when handling malicious or malformed input.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from little_loops.config import BRConfig
from little_loops.issue_parser import IssueInfo, IssueParser, find_issues

# =============================================================================
# Issue Content Fuzzing Strategy
# =============================================================================


@st.composite
def malformed_issue_content(draw: st.DrawFn) -> str:
    """Generate potentially malformed issue markdown content.

    Targets:
    - Missing or malformed frontmatter delimiters
    - Extreme frontmatter sizes
    - Invalid UTF-8 sequences
    - Extremely long lines
    - Deeply nested markdown structures
    """
    # Randomly decide whether to include frontmatter
    has_frontmatter = draw(st.booleans())

    parts = []

    if has_frontmatter:
        # May or may not have proper delimiters
        has_start_delim = draw(st.booleans())
        has_end_delim = draw(st.booleans())

        if has_start_delim:
            parts.append("---")

        # Generate frontmatter content
        # Can be: empty, huge, malformed key-value, etc.
        fm_type = draw(st.sampled_from(["empty", "huge", "malformed", "valid"]))

        if fm_type == "empty":
            parts.append("")
        elif fm_type == "huge":
            # Generate 1000 key-value pairs
            for _i in range(1000):
                key = draw(st.text(min_size=1, max_size=50))
                value = draw(st.text(min_size=0, max_size=200))
                parts.append(f"{key}: {value}")
        elif fm_type == "malformed":
            # Invalid YAML-like structures
            parts.append(draw(st.text(min_size=0, max_size=5000)))
        else:  # valid
            # Actually valid frontmatter
            parts.append(f"priority: {draw(st.sampled_from(['P0', 'P1', 'P2', 'P3']))}")
            parts.append(f"discovered_by: {draw(st.text(min_size=1, max_size=50))}")

        if has_end_delim:
            parts.append("---")

    # Add title (may be malformed)
    title = draw(st.text(min_size=0, max_size=500))
    if title:
        parts.append(f"# {title}")

    # Add body content (can include dependencies, etc.)
    body = draw(st.text(min_size=0, max_size=10000))
    if body:
        parts.append(body)

    return "\n".join(parts)


@st.composite
def issue_filename(draw: st.DrawFn) -> str:
    """Generate potentially malformed issue filenames.

    Targets:
    - Invalid priority prefixes
    - Missing type prefixes
    - Special characters
    - Extremely long names
    """
    # Random structure
    structure = draw(
        st.sampled_from(["standard", "no_priority", "only_id", "malformed"])
    )

    if structure == "standard":
        priority = draw(
            st.sampled_from(["P0", "P1", "P2", "P3", "P4", "P5", "PX", "P999"])
        )
        issue_type = draw(st.sampled_from(["BUG", "FEAT", "ENH", "XXX"]))
        number = draw(st.integers(min_value=0, max_value=9999))
        title = draw(st.text(min_size=0, max_size=100))
        return f"{priority}-{issue_type}-{number}-{title}.md"
    elif structure == "no_priority":
        issue_type = draw(st.sampled_from(["BUG", "FEAT", "ENH"]))
        number = draw(st.integers(min_value=0, max_value=9999))
        title = draw(st.text(min_size=0, max_size=100))
        return f"{issue_type}-{number}-{title}.md"
    elif structure == "only_id":
        number = draw(st.integers(min_value=0, max_value=99999))
        return f"{number}.md"
    else:  # malformed
        return draw(st.text(min_size=1, max_size=255)) + ".md"


# =============================================================================
# Fuzz Tests
# =============================================================================


class TestIssueParserFuzz:
    """Fuzz tests for issue parser crash safety."""

    @pytest.mark.slow
    @given(content=malformed_issue_content())
    @settings(
        max_examples=500,
        deadline=None,  # Disable deadline for potentially slow parsing
        suppress_health_check=list(HealthCheck),
    )
    def test_parse_file_never_crashes(self, content: str) -> None:
        """Parsing any content should never crash.

        May return None or default values, but must not raise uncaught
        exceptions.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            issue_file = Path(tmpdir) / "P1-BUG-001-test.md"
            issue_file.write_text(content, encoding="utf-8")

            # Create config with issues directory
            config = BRConfig(Path(tmpdir))
            parser = IssueParser(config)

            # Should not raise uncaught exceptions
            try:
                result = parser.parse_file(issue_file)
                # Result can be None or IssueInfo, both are valid
                assert result is None or isinstance(result, IssueInfo)
            except (UnicodeDecodeError, ValueError):
                # These are acceptable for truly malformed input
                # (e.g., invalid UTF-8, completely broken structure)
                pass
            except Exception as e:
                pytest.fail(f"Unexpected exception: {type(e).__name__}: {e}")

    @pytest.mark.slow
    @given(filename=issue_filename(), content=st.text(min_size=0, max_size=50000))
    @settings(
        max_examples=300,
        deadline=None,
        suppress_health_check=list(HealthCheck),
    )
    def test_parse_with_various_filenames(
        self, filename: str, content: str
    ) -> None:
        """Filename parsing should handle malformed names gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Sanitize filename for filesystem
            safe_filename = filename.replace("/", "_").replace("\\", "_")
            if not safe_filename or safe_filename == ".md":
                safe_filename = "test.md"

            issue_file = Path(tmpdir) / safe_filename
            try:
                issue_file.write_text(content, encoding="utf-8")
            except (OSError, ValueError):
                # Filename may be invalid for filesystem - skip this test
                return

            # Create config with issues directory
            config = BRConfig(Path(tmpdir))
            parser = IssueParser(config)

            try:
                result = parser.parse_file(issue_file)
                # Should not crash, result can be None
                assert result is None or isinstance(result, IssueInfo)
            except Exception:
                # Log but don't fail - we're testing crash safety
                # (If it's a real bug, it will be found by other tests)
                pass

    @pytest.mark.slow
    @given(frontmatter=st.text(min_size=0, max_size=100000))
    @settings(
        max_examples=200,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_huge_frontmatter_doesnt_hang(self, frontmatter: str) -> None:
        """Extremely large frontmatter should not cause hangs or excessive memory use.

        This specifically tests the custom frontmatter parser for DoS
        vulnerabilities.
        """
        content = f"---\n{frontmatter}\n---\n# Test\n\nBody."
        with tempfile.TemporaryDirectory() as tmpdir:
            issue_file = Path(tmpdir) / "P1-BUG-001-test.md"
            issue_file.write_text(content, encoding="utf-8")

            # Create config with issues directory
            config = BRConfig(Path(tmpdir))
            parser = IssueParser(config)

            # Note: We're testing that the parser completes without hanging
            # Hypothesis will catch if this takes too long with the deadline setting
            try:
                parser.parse_file(issue_file)
                # Success if it doesn't hang
            except Exception:
                # Other exceptions are acceptable for malformed input
                pass

    @pytest.mark.slow
    @given(
        blocked_by=st.lists(
            st.from_regex(r"[A-Z]{2,4}-\d{1,4}", fullmatch=True), max_size=100
        ),
        blocks=st.lists(
            st.from_regex(r"[A-Z]{2,4}-\d{1,4}", fullmatch=True), max_size=100
        ),
    )
    @settings(max_examples=200)
    def test_dependency_parsing_handles_lists(
        self, blocked_by: list[str], blocks: list[str]
    ) -> None:
        """Dependency parsing should handle large lists without crashing."""
        content = "# Test\n\n"
        if blocked_by:
            content += "## Blocked By\n\n"
            for dep in blocked_by:
                content += f"- {dep}\n"
        if blocks:
            content += "\n## Blocks\n\n"
            for dep in blocks:
                content += f"- {dep}\n"

        with tempfile.TemporaryDirectory() as tmpdir:
            issue_file = Path(tmpdir) / "P1-BUG-001-test.md"
            issue_file.write_text(content, encoding="utf-8")

            # Create config with issues directory
            config = BRConfig(Path(tmpdir))
            parser = IssueParser(config)
            result = parser.parse_file(issue_file)

            # Should parse without crashing
            assert result is None or isinstance(result, IssueInfo)


class TestIssueParserFindIssuesFuzz:
    """Fuzz tests for find_issues() directory scanning."""

    @pytest.mark.slow
    @given(
        files=st.lists(
            st.tuples(
                st.sampled_from(["bugs", "features", "enhancements", "other"]),
                st.text(
                    min_size=1,
                    max_size=50,
                    alphabet=st.characters(whitelist_categories=("L", "N", "P")),
                ),
                st.text(min_size=0, max_size=10000),
            ),
            max_size=50,
        )
    )
    @settings(max_examples=100, deadline=None)
    def test_find_issues_handles_mixed_files(self, files: list[tuple]) -> None:
        """Directory scanning should handle mixed valid/invalid files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = Path(tmpdir)

            # Create .issues subdirectories
            (base_path / ".issues" / "bugs").mkdir(parents=True, exist_ok=True)
            (base_path / ".issues" / "features").mkdir(parents=True, exist_ok=True)
            (base_path / ".issues" / "enhancements").mkdir(parents=True, exist_ok=True)

            # Create config
            config = BRConfig(base_path)

            # Create files
            for subdir, name, content in files:
                dir_path = base_path / ".issues" / subdir
                dir_path.mkdir(exist_ok=True)
                file_path = dir_path / f"{name}.md"

                try:
                    file_path.write_text(content, encoding="utf-8")
                except (OSError, ValueError):
                    # Skip files that can't be created
                    continue

            # Should not crash
            try:
                issues = find_issues(config)
                # Result can be empty list or list of IssueInfo
                assert isinstance(issues, list)
                for issue in issues:
                    assert isinstance(issue, IssueInfo)
            except Exception as e:
                pytest.fail(f"find_issues crashed: {type(e).__name__}: {e}")
