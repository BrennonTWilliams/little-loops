"""Tests for file hint extraction."""

import pytest

from little_loops.parallel.file_hints import (
    FileHints,
    _directories_overlap,
    _file_in_directory,
    _is_valid_path,
    extract_file_hints,
)


class TestFileHintExtraction:
    """Tests for extract_file_hints function."""

    def test_extracts_python_files(self) -> None:
        """Should extract .py file paths."""
        content = "Fix the bug in `scripts/little_loops/cli.py`"
        hints = extract_file_hints(content)
        assert "scripts/little_loops/cli.py" in hints.files

    def test_extracts_typescript_files(self) -> None:
        """Should extract .ts and .tsx file paths."""
        # Paths need a delimiter (space, backtick, etc.) before them
        content = "Modified `src/components/Button.tsx` and `utils/helpers.ts`"
        hints = extract_file_hints(content)
        assert "src/components/Button.tsx" in hints.files
        assert "utils/helpers.ts" in hints.files

    def test_extracts_multiple_files_from_content(self) -> None:
        """Should extract multiple file references."""
        content = """
        This issue affects:
        - scripts/little_loops/cli.py
        - scripts/little_loops/config.py
        - tests/test_cli.py
        """
        hints = extract_file_hints(content)
        assert "scripts/little_loops/cli.py" in hints.files
        assert "scripts/little_loops/config.py" in hints.files
        assert "tests/test_cli.py" in hints.files

    def test_extracts_directories(self) -> None:
        """Should extract directory paths."""
        content = "Changes to scripts/little_loops/ directory"
        hints = extract_file_hints(content)
        assert "scripts/little_loops/" in hints.directories

    def test_extracts_scopes(self) -> None:
        """Should extract scope identifiers."""
        content = "scope: sidebar\nComponent: auth-flow"
        hints = extract_file_hints(content)
        assert "sidebar" in hints.scopes

    def test_extracts_module_scope(self) -> None:
        """Should extract module identifiers."""
        content = "module: parallel-processing"
        hints = extract_file_hints(content)
        assert "parallel-processing" in hints.scopes

    def test_filters_urls(self) -> None:
        """Should filter out URLs."""
        content = "See https://example.com/path/file.py for details"
        hints = extract_file_hints(content)
        assert not any("example.com" in f for f in hints.files)

    def test_filters_short_paths(self) -> None:
        """Should filter out paths that are too short."""
        # Note: The regex still extracts short paths, but _is_valid_path filters them
        # "a.py" is 4 chars which passes the length check
        # We should test with paths shorter than 3 chars
        content = "Change `x` to `y`"  # Single character paths
        hints = extract_file_hints(content)
        # These are too short (< 3 chars)
        assert "x" not in hints.files
        assert "y" not in hints.files

    def test_stores_issue_id(self) -> None:
        """Should store the issue ID."""
        hints = extract_file_hints("content", "ENH-143")
        assert hints.issue_id == "ENH-143"

    def test_extracts_from_code_blocks(self) -> None:
        """Should extract file paths mentioned in code blocks."""
        content = """
        ```bash
        # Edit the file
        vim scripts/little_loops/cli.py
        ```
        """
        hints = extract_file_hints(content)
        assert "scripts/little_loops/cli.py" in hints.files

    def test_json_and_yaml_files(self) -> None:
        """Should extract config file types."""
        # Paths need a delimiter before them
        content = "Update `config.json` and `settings.yaml`"
        hints = extract_file_hints(content)
        assert "config.json" in hints.files
        assert "settings.yaml" in hints.files


class TestFileHintsOverlap:
    """Tests for FileHints.overlaps_with method."""

    def test_exact_file_match(self) -> None:
        """Should detect exact file matches."""
        hints1 = FileHints(files={"src/cli.py"})
        hints2 = FileHints(files={"src/cli.py", "src/other.py"})
        assert hints1.overlaps_with(hints2)

    def test_no_file_overlap(self) -> None:
        """Should return False for non-overlapping files."""
        hints1 = FileHints(files={"src/cli.py"})
        hints2 = FileHints(files={"src/other.py"})
        assert not hints1.overlaps_with(hints2)

    def test_directory_contains_file(self) -> None:
        """Should detect when a directory contains a file."""
        hints1 = FileHints(directories={"src/"})
        hints2 = FileHints(files={"src/cli.py"})
        assert hints1.overlaps_with(hints2)

    def test_file_in_directory_reverse(self) -> None:
        """Should detect file in directory overlap in both directions."""
        hints1 = FileHints(files={"src/cli.py"})
        hints2 = FileHints(directories={"src/"})
        assert hints1.overlaps_with(hints2)

    def test_nested_directories(self) -> None:
        """Should detect nested directory overlap."""
        hints1 = FileHints(directories={"src/"})
        hints2 = FileHints(directories={"src/components/"})
        assert hints1.overlaps_with(hints2)

    def test_scope_match(self) -> None:
        """Should detect scope matches."""
        hints1 = FileHints(scopes={"sidebar"})
        hints2 = FileHints(scopes={"sidebar", "auth"})
        assert hints1.overlaps_with(hints2)

    def test_scope_no_match(self) -> None:
        """Should not match different scopes."""
        hints1 = FileHints(scopes={"sidebar"})
        hints2 = FileHints(scopes={"auth"})
        assert not hints1.overlaps_with(hints2)

    def test_empty_hints_no_overlap(self) -> None:
        """Empty hints should not overlap."""
        hints1 = FileHints()
        hints2 = FileHints(files={"src/cli.py"})
        assert not hints1.overlaps_with(hints2)

    def test_both_empty_no_overlap(self) -> None:
        """Two empty hints should not overlap."""
        hints1 = FileHints()
        hints2 = FileHints()
        assert not hints1.overlaps_with(hints2)

    def test_all_paths_property(self) -> None:
        """all_paths should combine files and directories."""
        hints = FileHints(files={"a.py", "b.py"}, directories={"src/", "tests/"})
        assert hints.all_paths == {"a.py", "b.py", "src/", "tests/"}

    def test_is_empty_property(self) -> None:
        """is_empty should return True only when no hints."""
        assert FileHints().is_empty
        assert not FileHints(files={"a.py"}).is_empty
        assert not FileHints(directories={"src/"}).is_empty
        assert not FileHints(scopes={"auth"}).is_empty


class TestDirectoriesOverlap:
    """Tests for _directories_overlap helper."""

    def test_same_directory(self) -> None:
        """Same directory should overlap."""
        assert _directories_overlap("src/", "src/")

    def test_parent_child(self) -> None:
        """Parent and child directories should overlap."""
        assert _directories_overlap("src/", "src/components/")
        assert _directories_overlap("src/components/", "src/")

    def test_siblings(self) -> None:
        """Sibling directories should not overlap."""
        assert not _directories_overlap("src/", "tests/")

    def test_trailing_slash_handling(self) -> None:
        """Should handle inconsistent trailing slashes."""
        assert _directories_overlap("src", "src/")
        assert _directories_overlap("src/", "src")


class TestFileInDirectory:
    """Tests for _file_in_directory helper."""

    def test_file_in_dir(self) -> None:
        """Should detect file in directory."""
        assert _file_in_directory("src/cli.py", "src/")
        assert _file_in_directory("src/components/Button.tsx", "src/")

    def test_file_not_in_dir(self) -> None:
        """Should return False for file not in directory."""
        assert not _file_in_directory("tests/test.py", "src/")

    def test_handles_trailing_slash(self) -> None:
        """Should handle trailing slash on directory."""
        assert _file_in_directory("src/cli.py", "src")
        assert _file_in_directory("src/cli.py", "src/")


class TestIsValidPath:
    """Tests for _is_valid_path filter."""

    def test_valid_paths(self) -> None:
        """Should accept valid file paths."""
        assert _is_valid_path("src/cli.py")
        assert _is_valid_path("tests/test_cli.py")
        assert _is_valid_path("config.json")

    def test_filters_urls(self) -> None:
        """Should reject URLs."""
        assert not _is_valid_path("https://example.com/file.py")
        assert not _is_valid_path("http://example.com/file.py")
        assert not _is_valid_path("//network/share/file.py")

    def test_filters_short_paths(self) -> None:
        """Should reject very short paths."""
        assert not _is_valid_path("a")
        assert not _is_valid_path("ab")

    def test_filters_extension_only(self) -> None:
        """Should reject paths that are just extensions."""
        assert not _is_valid_path(".py")
        assert not _is_valid_path(".ts")

    def test_filters_common_false_positives(self) -> None:
        """Should reject common false positives."""
        assert not _is_valid_path("e.g.")
        assert not _is_valid_path("i.e.")
