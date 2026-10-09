"""Scan scope canonicalization and the literal Git-path matcher (FEAT-3713 step 2)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from little_loops.git_operations import file_matches_pattern
from little_loops.next_arena.actions import scan_scope_hash
from little_loops.next_arena.scan_state import (
    DIR_INVALID,
    DIR_MISSING,
    DIR_NOT_DIRECTORY,
    DIR_OK,
    DIR_SYMLINK,
    canonical_exclude_patterns,
    normalize_scan_dir,
    path_in_scope,
    resolve_scan_scope,
)

ROOT = Path("/proj")


# ------------------------------------------------------------------------------ matcher


def test_default_matcher_is_unchanged_and_converts_file_backslashes() -> None:
    # existing callers keep their normalizing behavior byte for byte
    assert file_matches_pattern("src/a\\b.py", "src/a/b.py") is True
    assert file_matches_pattern("src/a/b.py", "src/a/b.py") is True
    assert file_matches_pattern("pkg/node_modules/x.js", "**/node_modules/**") is True
    assert file_matches_pattern("a/b.pyc", "*.pyc") is True


def test_literal_matcher_keeps_backslash_and_newline_filenames_distinct() -> None:
    literal, different = "src/a\\b.py", "src/a/b.py"
    # the exact exclusion of the slash-separated path must not suppress the literal one
    assert file_matches_pattern(different, "src/a/b.py", literal_path=True) is True
    assert file_matches_pattern(literal, "src/a/b.py", literal_path=True) is False
    assert file_matches_pattern(literal, "src/a/b.py") is True  # the unchanged normalizer
    # basename matching uses only "/" as a separator
    assert file_matches_pattern("x/a\\b.py", "a\\b.py", literal_path=True) is False
    assert file_matches_pattern("x/a\\b.py", "*.py", literal_path=True) is True
    assert file_matches_pattern("src/line\nbreak.py", "src/*.py", literal_path=True) is True
    assert (
        file_matches_pattern("src/line\nbreak.py", "src/line/break.py", literal_path=True) is False
    )


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("src/a.py", True),
        ("src", True),
        ("src-extra/a.py", False),  # a textual prefix is not a directory prefix
        ("srcx", False),
        ("other/src/a.py", False),
        ("src/vendor/x.py", False),  # excluded
        ("src/a\\b.py", True),  # literal backslash is just a character
    ],
)
def test_scope_membership_uses_directory_prefix_and_exclusions(path: str, expected: bool) -> None:
    assert path_in_scope(path, ["src"], ["src/vendor/**"]) is expected


def test_literal_backslash_exclusion_does_not_suppress_the_slash_separated_path() -> None:
    # fixture pair from the issue: the exclusion names the slash-separated path exactly
    assert path_in_scope("src/a/b.py", ["src"], ["src/a/b.py"]) is False
    assert path_in_scope("src/a\\b.py", ["src"], ["src/a/b.py"]) is True


def test_empty_focus_dirs_is_an_empty_scope_and_root_is_everything() -> None:
    assert path_in_scope("src/a.py", [], []) is False  # unlike codegraph's unrestricted default
    assert path_in_scope("anything/at/all.py", ["."], []) is True
    assert path_in_scope("a/__pycache__/x.pyc", ["."], ["**/__pycache__/**"]) is False


# ------------------------------------------------------------------------ normalization


@pytest.mark.parametrize(
    ("configured", "expected"),
    [
        ("src", "src"),
        ("src/", "src"),
        ("./src/", "src"),
        ("src//lib/", "src/lib"),
        ("src/./lib", "src/lib"),
        ("a/b/../c", "a/c"),
        (".", "."),
        ("./", "."),
        ("/", "."),
        ("src\\lib", "src/lib"),  # configured syntax, not a Git-emitted path
        ("/proj/src", "src"),
        ("/proj", "."),
    ],
)
def test_normalize_valid_directories(configured: str, expected: str) -> None:
    assert normalize_scan_dir(configured, ROOT) == (expected, "")


@pytest.mark.parametrize(
    "configured", ["", "  ", "..", "../x", "a/../../x", "/elsewhere/src", "a\x00b", 7, None]
)
def test_normalize_rejects_invalid_directories(configured: object) -> None:
    normalized, reason = normalize_scan_dir(configured, ROOT)
    assert normalized is None and reason


def test_equivalent_spellings_and_orderings_share_one_scope_hash(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "lib").mkdir()
    a = resolve_scan_scope(["src/", "./lib"], ["b*", "a*"], tmp_path)
    b = resolve_scan_scope(["lib", "src", "./src/"], ["a*", "b*", "a*"], tmp_path)
    assert a.focus_dirs == b.focus_dirs == ("lib", "src")
    assert a.exclude_patterns == b.exclude_patterns == ("a*", "b*")
    assert a.scope_hash == b.scope_hash == scan_scope_hash(("lib", "src"), ("a*", "b*"))
    # changing exclusions or directory meaning changes identity
    assert resolve_scan_scope(["src"], ["a*"], tmp_path).scope_hash != a.scope_hash
    assert (
        resolve_scan_scope(["src", "lib"], ["a*", "b*", "c*"], tmp_path).scope_hash != a.scope_hash
    )


def test_exclude_patterns_are_deduplicated_sorted_and_validated() -> None:
    kept, diagnostics = canonical_exclude_patterns(["**/b/**", "**/a/**", "**/b/**", "", None, 3])
    assert kept == ("**/a/**", "**/b/**")
    assert [d.code for d in diagnostics] == ["scan_exclude_ignored"] * 3


# --------------------------------------------------------------- filesystem eligibility


def test_missing_directory_is_dropped_while_another_remains(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    scope = resolve_scan_scope(["src", "gone"], [], tmp_path)
    assert scope.failure is None
    assert scope.focus_dirs == ("src",)
    assert {d.configured: d.status for d in scope.directories} == {
        "src": DIR_OK,
        "gone": DIR_MISSING,
    }
    assert [d.code for d in scope.diagnostics] == ["scan_dir_missing"]


def test_only_missing_directories_fails_the_whole_scope(tmp_path: Path) -> None:
    scope = resolve_scan_scope(["nope", "nada"], [], tmp_path)
    assert scope.failure is not None and scope.failure[0] == "scope_no_existing_directory"
    assert scope.focus_dirs == ()
    # the target still hashes the declared (valid-syntax) scope so --explain can resolve it
    assert scope.scope_hash == scan_scope_hash(("nada", "nope"), ())


def test_empty_scope_is_diagnosed(tmp_path: Path) -> None:
    scope = resolve_scan_scope([], [], tmp_path)
    assert scope.failure is not None and scope.failure[0] == "scope_empty"


def test_invalid_entry_fails_the_whole_scope_even_beside_a_good_one(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    scope = resolve_scan_scope(["src", "../escape"], [], tmp_path)
    assert scope.failure is not None and scope.failure[0] == "scope_invalid"
    assert {d.status for d in scope.directories} == {DIR_OK, DIR_INVALID}


def test_regular_file_is_not_an_eligible_directory(tmp_path: Path) -> None:
    (tmp_path / "file.txt").write_text("x")
    scope = resolve_scan_scope(["file.txt"], [], tmp_path)
    assert scope.directories[0].status == DIR_NOT_DIRECTORY
    assert scope.failure is not None


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlinks unavailable")
class TestSymlinkScopes:
    def test_final_component_alias_inside_the_project_is_unsupported(self, tmp_path: Path) -> None:
        (tmp_path / "src").mkdir()
        (tmp_path / "alias").symlink_to("src", target_is_directory=True)
        scope = resolve_scan_scope(["alias"], [], tmp_path)
        assert scope.directories[0].status == DIR_SYMLINK
        assert scope.failure is not None and scope.failure[0] == "symlink_scope_unsupported"
        assert scope.focus_dirs == ()  # no partial-scope offer and no silent resolution

    def test_symlink_pointing_outside_the_project_is_unsupported(self, tmp_path: Path) -> None:
        outside = tmp_path / "outside"
        outside.mkdir()
        project = tmp_path / "project"
        project.mkdir()
        (project / "ext").symlink_to(outside, target_is_directory=True)
        scope = resolve_scan_scope(["ext"], [], project)
        assert scope.failure is not None and scope.failure[0] == "symlink_scope_unsupported"

    def test_intermediate_alias_component_is_unsupported(self, tmp_path: Path) -> None:
        (tmp_path / "real" / "lib").mkdir(parents=True)
        (tmp_path / "alias").symlink_to("real", target_is_directory=True)
        scope = resolve_scan_scope(["alias/lib"], [], tmp_path)
        assert scope.directories[0].status == DIR_SYMLINK
        assert scope.failure is not None and scope.failure[0] == "symlink_scope_unsupported"

    def test_a_symlink_vetoes_the_whole_scope_not_just_its_entry(self, tmp_path: Path) -> None:
        (tmp_path / "src").mkdir()
        (tmp_path / "alias").symlink_to("src", target_is_directory=True)
        scope = resolve_scan_scope(["src", "alias"], [], tmp_path)
        assert scope.failure is not None and scope.failure[0] == "symlink_scope_unsupported"
        assert scope.focus_dirs == ("src",)  # the physical entry is still described
