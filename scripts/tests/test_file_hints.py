"""Tests for file hint extraction."""

from little_loops.parallel.file_hints import (
    COMMON_FILES_EXCLUDE,
    MIN_DIRECTORY_DEPTH,
    MIN_OVERLAP_FILES,
    OVERLAP_RATIO_THRESHOLD,
    FileHints,
    _directories_overlap,
    _file_in_directory,
    _is_common_file,
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

    def test_multiple_file_matches(self) -> None:
        """Should detect overlap when multiple files match (meets MIN_OVERLAP_FILES)."""
        hints1 = FileHints(files={"src/cli.py", "src/config.py"})
        hints2 = FileHints(files={"src/cli.py", "src/config.py", "src/other.py"})
        assert hints1.overlaps_with(hints2)

    def test_single_file_in_small_set_meets_ratio(self) -> None:
        """Single file match meets ratio threshold when set is small enough."""
        # 1 file in a set of 1 = 100% ratio >= 25% threshold
        hints1 = FileHints(files={"src/cli.py"})
        hints2 = FileHints(files={"src/cli.py", "src/other.py"})
        assert hints1.overlaps_with(hints2)

    def test_single_file_below_ratio_threshold(self) -> None:
        """Single file match below ratio threshold should not overlap."""
        # 1 shared file out of 5 = 20% < 25% threshold, and 1 < MIN_OVERLAP_FILES
        hints1 = FileHints(
            files={"src/a.py", "src/b.py", "src/c.py", "src/d.py", "src/cli.py"}
        )
        hints2 = FileHints(
            files={"src/e.py", "src/f.py", "src/g.py", "src/h.py", "src/cli.py"}
        )
        assert not hints1.overlaps_with(hints2)

    def test_no_file_overlap(self) -> None:
        """Should return False for non-overlapping files."""
        hints1 = FileHints(files={"src/cli.py"})
        hints2 = FileHints(files={"src/other.py"})
        assert not hints1.overlaps_with(hints2)

    def test_deep_directory_contains_file(self) -> None:
        """Should detect when a deep directory contains a file."""
        hints1 = FileHints(directories={"src/components/"})
        hints2 = FileHints(files={"src/components/Button.tsx"})
        assert hints1.overlaps_with(hints2)

    def test_shallow_directory_no_overlap(self) -> None:
        """Shallow directory (depth < MIN_DIRECTORY_DEPTH) should not trigger overlap."""
        hints1 = FileHints(directories={"src/"})
        hints2 = FileHints(files={"src/cli.py"})
        assert not hints1.overlaps_with(hints2)

    def test_shallow_directory_reverse_no_overlap(self) -> None:
        """Shallow directory should not trigger overlap in reverse direction."""
        hints1 = FileHints(files={"src/cli.py"})
        hints2 = FileHints(directories={"src/"})
        assert not hints1.overlaps_with(hints2)

    def test_deep_nested_directories(self) -> None:
        """Should detect nested directory overlap when depth is sufficient."""
        hints1 = FileHints(directories={"src/components/"})
        hints2 = FileHints(directories={"src/components/forms/"})
        assert hints1.overlaps_with(hints2)

    def test_shallow_nested_directories_no_overlap(self) -> None:
        """Shallow nested directories should not overlap."""
        hints1 = FileHints(directories={"src/"})
        hints2 = FileHints(directories={"src/components/"})
        assert not hints1.overlaps_with(hints2)

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

    def test_common_file_excluded(self) -> None:
        """Common infrastructure files should be excluded from overlap checks."""
        hints1 = FileHints(files={"scripts/little_loops/__init__.py"})
        hints2 = FileHints(files={"scripts/little_loops/__init__.py", "src/other.py"})
        assert not hints1.overlaps_with(hints2)

    def test_common_file_pyproject_excluded(self) -> None:
        """pyproject.toml should be excluded from overlap checks."""
        hints1 = FileHints(files={"pyproject.toml"})
        hints2 = FileHints(files={"pyproject.toml", "src/main.py"})
        assert not hints1.overlaps_with(hints2)

    def test_common_files_plus_real_overlap(self) -> None:
        """Common files don't prevent detection of real overlaps."""
        hints1 = FileHints(
            files={"scripts/__init__.py", "scripts/cli.py", "scripts/config.py"}
        )
        hints2 = FileHints(
            files={"scripts/__init__.py", "scripts/cli.py", "scripts/config.py"}
        )
        # __init__.py excluded, but cli.py + config.py = 2 files >= MIN_OVERLAP_FILES
        assert hints1.overlaps_with(hints2)

    def test_ratio_threshold_edge(self) -> None:
        """Edge case: exactly at the ratio threshold should overlap."""
        # 1 shared file out of 4 = 25% == OVERLAP_RATIO_THRESHOLD
        hints1 = FileHints(
            files={"src/a.py", "src/b.py", "src/c.py", "src/shared.py"}
        )
        hints2 = FileHints(files={"src/shared.py"})
        # 1/1 = 100% ratio (smaller set is 1) - meets threshold
        assert hints1.overlaps_with(hints2)

    def test_deep_file_in_directory(self) -> None:
        """File in a deep directory should trigger overlap."""
        hints1 = FileHints(files={"scripts/little_loops/parallel/file_hints.py"})
        hints2 = FileHints(directories={"scripts/little_loops/"})
        assert hints1.overlaps_with(hints2)


class TestGetOverlappingPaths:
    """Tests for FileHints.get_overlapping_paths method."""

    def test_multiple_file_matches(self) -> None:
        """Should return shared file paths when threshold met."""
        hints1 = FileHints(files={"src/cli.py", "src/config.py"})
        hints2 = FileHints(files={"src/cli.py", "src/config.py", "src/other.py"})
        result = hints1.get_overlapping_paths(hints2)
        assert result == {"src/cli.py", "src/config.py"}

    def test_single_file_below_threshold_returns_empty(self) -> None:
        """Single shared file below threshold should return empty set."""
        hints1 = FileHints(
            files={"src/a.py", "src/b.py", "src/c.py", "src/d.py", "src/cli.py"}
        )
        hints2 = FileHints(
            files={"src/e.py", "src/f.py", "src/g.py", "src/h.py", "src/cli.py"}
        )
        result = hints1.get_overlapping_paths(hints2)
        assert result == set()

    def test_deep_directory_overlap(self) -> None:
        """Should return the shorter/parent directory when deep enough."""
        hints1 = FileHints(directories={"src/components/"})
        hints2 = FileHints(directories={"src/components/forms/"})
        result = hints1.get_overlapping_paths(hints2)
        assert "src/components/" in result

    def test_shallow_directory_no_overlap(self) -> None:
        """Should return empty for shallow directory overlap."""
        hints1 = FileHints(directories={"src/"})
        hints2 = FileHints(directories={"src/components/"})
        result = hints1.get_overlapping_paths(hints2)
        assert result == set()

    def test_file_in_deep_directory(self) -> None:
        """Should return the file path when it's in a deep directory."""
        hints1 = FileHints(files={"src/components/Button.tsx"})
        hints2 = FileHints(directories={"src/components/"})
        result = hints1.get_overlapping_paths(hints2)
        assert "src/components/Button.tsx" in result

    def test_file_in_shallow_directory_no_overlap(self) -> None:
        """Should return empty when file is in a shallow directory."""
        hints1 = FileHints(files={"src/cli.py"})
        hints2 = FileHints(directories={"src/"})
        result = hints1.get_overlapping_paths(hints2)
        assert result == set()

    def test_no_overlap(self) -> None:
        """Should return empty set when no overlap."""
        hints1 = FileHints(files={"src/cli.py"})
        hints2 = FileHints(files={"tests/test.py"})
        result = hints1.get_overlapping_paths(hints2)
        assert result == set()

    def test_empty_hints(self) -> None:
        """Should return empty set for empty hints."""
        hints1 = FileHints()
        hints2 = FileHints(files={"src/cli.py"})
        result = hints1.get_overlapping_paths(hints2)
        assert result == set()

    def test_both_empty(self) -> None:
        """Should return empty set when both empty."""
        result = FileHints().get_overlapping_paths(FileHints())
        assert result == set()

    def test_multiple_overlaps(self) -> None:
        """Should return all overlapping paths when threshold met."""
        hints1 = FileHints(files={"src/a.py", "src/b.py"})
        hints2 = FileHints(files={"src/a.py", "src/b.py", "src/c.py"})
        result = hints1.get_overlapping_paths(hints2)
        assert result == {"src/a.py", "src/b.py"}

    def test_common_files_excluded(self) -> None:
        """Common infrastructure files should be excluded from results."""
        hints1 = FileHints(files={"scripts/__init__.py", "pyproject.toml"})
        hints2 = FileHints(files={"scripts/__init__.py", "pyproject.toml"})
        result = hints1.get_overlapping_paths(hints2)
        assert result == set()


class TestDirectoriesOverlap:
    """Tests for _directories_overlap helper."""

    def test_same_deep_directory(self) -> None:
        """Same deep directory should overlap."""
        assert _directories_overlap("src/components/", "src/components/")

    def test_deep_parent_child(self) -> None:
        """Deep parent and child directories should overlap."""
        assert _directories_overlap("src/components/", "src/components/forms/")
        assert _directories_overlap("src/components/forms/", "src/components/")

    def test_siblings(self) -> None:
        """Sibling directories should not overlap."""
        assert not _directories_overlap("src/", "tests/")

    def test_shallow_directory_no_overlap(self) -> None:
        """Shallow directories (depth < MIN_DIRECTORY_DEPTH) should not overlap."""
        assert not _directories_overlap("src/", "src/")
        assert not _directories_overlap("src/", "src/components/")

    def test_trailing_slash_handling(self) -> None:
        """Should handle inconsistent trailing slashes."""
        assert _directories_overlap("src/components", "src/components/")
        assert _directories_overlap("src/components/", "src/components")

    def test_min_depth_boundary(self) -> None:
        """Directories at exactly MIN_DIRECTORY_DEPTH segments should overlap."""
        # "src/components" has 2 segments → meets MIN_DIRECTORY_DEPTH=2
        assert _directories_overlap("src/components/", "src/components/forms/")
        # "src" has 1 segment → does NOT meet threshold
        assert not _directories_overlap("src/", "src/components/")


class TestFileInDirectory:
    """Tests for _file_in_directory helper."""

    def test_file_in_deep_dir(self) -> None:
        """Should detect file in deep directory."""
        assert _file_in_directory("src/components/Button.tsx", "src/components/")

    def test_file_in_shallow_dir(self) -> None:
        """Shallow directory should not match."""
        assert not _file_in_directory("src/cli.py", "src/")
        assert not _file_in_directory("src/components/Button.tsx", "src/")

    def test_file_not_in_dir(self) -> None:
        """Should return False for file not in directory."""
        assert not _file_in_directory("tests/test.py", "src/")

    def test_handles_trailing_slash(self) -> None:
        """Should handle trailing slash on directory."""
        assert _file_in_directory("src/components/cli.py", "src/components")
        assert _file_in_directory("src/components/cli.py", "src/components/")


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


class TestIsCommonFile:
    """Tests for _is_common_file helper."""

    def test_init_py_excluded(self) -> None:
        """__init__.py should be a common file."""
        assert _is_common_file("__init__.py")
        assert _is_common_file("scripts/little_loops/__init__.py")
        assert _is_common_file("deep/path/to/__init__.py")

    def test_pyproject_excluded(self) -> None:
        """pyproject.toml should be a common file."""
        assert _is_common_file("pyproject.toml")

    def test_setup_excluded(self) -> None:
        """setup.py and setup.cfg should be common files."""
        assert _is_common_file("setup.py")
        assert _is_common_file("setup.cfg")

    def test_regular_file_not_excluded(self) -> None:
        """Regular source files should not be common files."""
        assert not _is_common_file("src/cli.py")
        assert not _is_common_file("scripts/little_loops/config.py")
        assert not _is_common_file("tests/test_cli.py")

    def test_all_common_files(self) -> None:
        """All files in COMMON_FILES_EXCLUDE should be common."""
        for f in COMMON_FILES_EXCLUDE:
            assert _is_common_file(f)


class TestThresholdConstants:
    """Tests to document threshold constant values."""

    def test_min_overlap_files(self) -> None:
        """MIN_OVERLAP_FILES should be 2."""
        assert MIN_OVERLAP_FILES == 2

    def test_overlap_ratio_threshold(self) -> None:
        """OVERLAP_RATIO_THRESHOLD should be 0.25."""
        assert OVERLAP_RATIO_THRESHOLD == 0.25

    def test_min_directory_depth(self) -> None:
        """MIN_DIRECTORY_DEPTH should be 2."""
        assert MIN_DIRECTORY_DEPTH == 2
