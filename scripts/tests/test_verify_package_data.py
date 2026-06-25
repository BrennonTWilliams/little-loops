"""Tests for ll-verify-package-data — __file__-escape lint."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from little_loops.cli.verify_package_data import (
    EscapeViolation,
    LintResult,
    _ALLOWLIST,
    _count_parent_steps,
    _file_depth,
    _lint_file,
    main_verify_package_data,
    run_escape_lint,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _re_match(pattern_text: str):
    """Return the first regex match for a Path(__file__) expression."""
    import re

    from little_loops.cli.verify_package_data import _FILE_ESCAPE_RE

    return _FILE_ESCAPE_RE.search(pattern_text)


def _make_pkg(tmp_path: Path) -> Path:
    """Create a minimal scripts/little_loops/ directory under tmp_path."""
    pkg = tmp_path / "scripts" / "little_loops"
    pkg.mkdir(parents=True)
    return pkg


# ---------------------------------------------------------------------------
# Unit tests: _count_parent_steps
# ---------------------------------------------------------------------------


class TestCountParentSteps:
    """Verify parent-traversal counting from regex matches."""

    def test_single_dot_parent(self) -> None:
        m = _re_match("Path(__file__).parent")
        assert m is not None
        assert _count_parent_steps(m) == 1

    def test_two_dot_parent(self) -> None:
        m = _re_match("Path(__file__).parent.parent")
        assert m is not None
        assert _count_parent_steps(m) == 2

    def test_three_dot_parent(self) -> None:
        m = _re_match("Path(__file__).parent.parent.parent")
        assert m is not None
        assert _count_parent_steps(m) == 3

    def test_four_dot_parent(self) -> None:
        m = _re_match("Path(__file__).resolve().parent.parent.parent.parent")
        assert m is not None
        assert _count_parent_steps(m) == 4

    def test_parents_bracket_zero(self) -> None:
        # .parents[0] == .parent → 1 step
        m = _re_match("Path(__file__).parents[0]")
        assert m is not None
        assert _count_parent_steps(m) == 1

    def test_parents_bracket_three(self) -> None:
        # .parents[3] → 4 steps
        m = _re_match("Path(__file__).resolve().parents[3]")
        assert m is not None
        assert _count_parent_steps(m) == 4

    def test_resolve_does_not_affect_count(self) -> None:
        # .resolve() between __file__ and .parent chain is transparent
        with_resolve = _re_match("Path(__file__).resolve().parent.parent")
        without_resolve = _re_match("Path(__file__).parent.parent")
        assert with_resolve is not None and without_resolve is not None
        assert _count_parent_steps(with_resolve) == _count_parent_steps(without_resolve)


# ---------------------------------------------------------------------------
# Unit tests: _file_depth
# ---------------------------------------------------------------------------


class TestFileDepth:
    """Verify depth calculation from package root."""

    def test_root_level_file(self, tmp_path: Path) -> None:
        pkg = _make_pkg(tmp_path)
        f = pkg / "logo.py"
        f.touch()
        assert _file_depth(f, pkg) == 0

    def test_one_subdir_file(self, tmp_path: Path) -> None:
        pkg = _make_pkg(tmp_path)
        (pkg / "hooks").mkdir()
        f = pkg / "hooks" / "user_prompt_submit.py"
        f.touch()
        assert _file_depth(f, pkg) == 1

    def test_two_subdir_file(self, tmp_path: Path) -> None:
        pkg = _make_pkg(tmp_path)
        (pkg / "cli" / "loop").mkdir(parents=True)
        f = pkg / "cli" / "loop" / "_helpers.py"
        f.touch()
        assert _file_depth(f, pkg) == 2


# ---------------------------------------------------------------------------
# Unit tests: _lint_file
# ---------------------------------------------------------------------------


class TestLintFile:
    """Per-file lint logic — verify escape detection and allowlist."""

    def _write(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    def test_no_violation_single_parent_depth_zero(self, tmp_path: Path) -> None:
        """logo.py pattern: depth=0, .parent → count=1, not an escape (1 > 1 is False)."""
        pkg = _make_pkg(tmp_path)
        f = pkg / "logo.py"
        self._write(f, 'logo_path = Path(__file__).parent / "assets" / "ll-cli-logo.txt"\n')
        result = _lint_file(f, pkg)
        assert not result.has_violations

    def test_violation_two_parents_depth_zero(self, tmp_path: Path) -> None:
        """depth=0, .parent.parent → count=2 → 2 > 1 = True → flagged."""
        pkg = _make_pkg(tmp_path)
        f = pkg / "bad.py"
        self._write(f, "p = Path(__file__).parent.parent / 'somewhere'\n")
        result = _lint_file(f, pkg)
        assert result.has_violations
        assert result.violations[0].parent_count == 2
        assert result.violations[0].depth == 0

    def test_violation_user_prompt_submit_pattern(self, tmp_path: Path) -> None:
        """depth=1, .parents[3] → count=4 → 4 > 2 = True → flagged (BUG-2275 pattern)."""
        pkg = _make_pkg(tmp_path)
        (pkg / "hooks").mkdir()
        f = pkg / "hooks" / "user_prompt_submit.py"
        self._write(
            f,
            '_PROMPT_FILE = Path(__file__).resolve().parents[3] / "hooks" / "prompts" / "x.md"\n',
        )
        result = _lint_file(f, pkg)
        assert result.has_violations
        assert result.violations[0].parent_count == 4
        assert result.violations[0].depth == 1

    def test_no_violation_helpers_pattern(self, tmp_path: Path) -> None:
        """depth=2, .parent×3 → count=3 → 3 > 3 is False → NOT flagged (_helpers.py pattern)."""
        pkg = _make_pkg(tmp_path)
        (pkg / "cli" / "loop").mkdir(parents=True)
        f = pkg / "cli" / "loop" / "_helpers.py"
        self._write(f, "loops_dir = Path(__file__).parent.parent.parent / 'loops'\n")
        result = _lint_file(f, pkg)
        assert not result.has_violations

    def test_no_violation_fragments_pattern(self, tmp_path: Path) -> None:
        """depth=1, .parent×2 → count=2 → 2 > 2 is False → NOT flagged (fragments.py pattern)."""
        pkg = _make_pkg(tmp_path)
        (pkg / "fsm").mkdir()
        f = pkg / "fsm" / "fragments.py"
        self._write(f, "_LOOPS = Path(__file__).parent.parent / 'loops'\n")
        result = _lint_file(f, pkg)
        assert not result.has_violations

    def test_allowlisted_file_not_flagged(self, tmp_path: Path) -> None:
        """Files on the allowlist are skipped even if they contain escaping patterns."""
        pkg = _make_pkg(tmp_path)
        # init/cli.py is on the allowlist
        (pkg / "init").mkdir()
        f = pkg / "init" / "cli.py"
        self._write(
            f,
            "def _plugin_root():\n"
            "    return Path(__file__).resolve().parent.parent.parent.parent\n",
        )
        result = _lint_file(f, pkg)
        assert not result.has_violations

    def test_no_file_escape_expression(self, tmp_path: Path) -> None:
        """File with no Path(__file__) usage → no violations."""
        pkg = _make_pkg(tmp_path)
        f = pkg / "pure.py"
        self._write(f, "x = 1\ny = 'hello'\n")
        result = _lint_file(f, pkg)
        assert not result.has_violations

    def test_multiple_violations_in_one_file(self, tmp_path: Path) -> None:
        """Multiple escaping lines in one file → multiple violations."""
        pkg = _make_pkg(tmp_path)
        f = pkg / "multi.py"
        self._write(
            f,
            "a = Path(__file__).parent.parent / 'x'\n"
            "b = Path(__file__).parent.parent.parent / 'y'\n",
        )
        result = _lint_file(f, pkg)
        assert len(result.violations) == 2

    def test_violation_line_number_correct(self, tmp_path: Path) -> None:
        """The reported line number matches where the escape occurs."""
        pkg = _make_pkg(tmp_path)
        f = pkg / "bad.py"
        self._write(f, "# comment\n# comment\np = Path(__file__).parent.parent\n")
        result = _lint_file(f, pkg)
        assert result.has_violations
        assert result.violations[0].line_no == 3


# ---------------------------------------------------------------------------
# Unit tests: run_escape_lint
# ---------------------------------------------------------------------------


class TestRunEscapeLint:
    """Full-package lint scan."""

    def test_clean_package_returns_empty(self, tmp_path: Path) -> None:
        """Package with only in-package reads → no results."""
        pkg = _make_pkg(tmp_path)
        (pkg / "logo.py").write_text(
            'p = Path(__file__).parent / "assets" / "ll-cli-logo.txt"\n'
        )
        results = run_escape_lint(pkg)
        assert results == []

    def test_package_with_one_escape(self, tmp_path: Path) -> None:
        """One escaping file → one result."""
        pkg = _make_pkg(tmp_path)
        (pkg / "hooks").mkdir()
        (pkg / "hooks" / "bad.py").write_text(
            "f = Path(__file__).resolve().parents[3] / 'x'\n"
        )
        results = run_escape_lint(pkg)
        assert len(results) == 1
        assert "hooks/bad.py" in results[0].rel_path

    def test_allowlisted_files_excluded(self, tmp_path: Path) -> None:
        """Allowlisted files do not appear in results even with escaping patterns."""
        pkg = _make_pkg(tmp_path)
        (pkg / "init").mkdir()
        # skill_expander.py is allowlisted
        (pkg / "skill_expander.py").write_text(
            "return Path(__file__).resolve().parent.parent.parent\n"
        )
        results = run_escape_lint(pkg)
        assert results == []


# ---------------------------------------------------------------------------
# Integration tests: main_verify_package_data
# ---------------------------------------------------------------------------


class TestMainVerifyPackageData:
    """CLI entry point tests."""

    def _pkg(self, tmp_path: Path) -> Path:
        pkg = tmp_path / "scripts" / "little_loops"
        pkg.mkdir(parents=True)
        return pkg

    def test_clean_directory_returns_zero(self, tmp_path: Path) -> None:
        """Clean source + --lint-only → exit 0."""
        pkg = self._pkg(tmp_path)
        (pkg / "ok.py").write_text('p = Path(__file__).parent / "assets"\n')
        with (
            patch("sys.argv", ["ll-verify-package-data", "-C", str(tmp_path), "--lint-only"]),
            patch("builtins.print"),
        ):
            assert main_verify_package_data() == 0

    def test_escaping_file_returns_one(self, tmp_path: Path) -> None:
        """File with __file__ escape + --lint-only → exit 1."""
        pkg = self._pkg(tmp_path)
        (pkg / "hooks").mkdir()
        (pkg / "hooks" / "bad.py").write_text(
            "_F = Path(__file__).resolve().parents[3] / 'x'\n"
        )
        with (
            patch("sys.argv", ["ll-verify-package-data", "-C", str(tmp_path), "--lint-only"]),
            patch("builtins.print"),
        ):
            assert main_verify_package_data() == 1

    def test_directory_not_found_returns_one(self, tmp_path: Path) -> None:
        """Non-existent -C path → exit 1."""
        with (
            patch(
                "sys.argv",
                ["ll-verify-package-data", "-C", str(tmp_path / "nonexistent"), "--lint-only"],
            ),
            patch("builtins.print"),
        ):
            assert main_verify_package_data() == 1

    def test_json_output_is_parseable(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """--json flag produces valid JSON output."""
        pkg = self._pkg(tmp_path)
        (pkg / "clean.py").write_text("x = 1\n")
        with patch(
            "sys.argv",
            ["ll-verify-package-data", "-C", str(tmp_path), "--json", "--lint-only"],
        ):
            ret = main_verify_package_data()
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "escape_violations" in data
        assert "missing_assets" in data
        assert "passed" in data
        assert ret == 0

    def test_json_output_contains_violations(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """--json flag includes violation details."""
        pkg = self._pkg(tmp_path)
        (pkg / "bad.py").write_text("p = Path(__file__).parent.parent\n")
        with patch(
            "sys.argv",
            ["ll-verify-package-data", "-C", str(tmp_path), "--json", "--lint-only"],
        ):
            main_verify_package_data()
        data = json.loads(capsys.readouterr().out)
        assert len(data["escape_violations"]) == 1
        assert data["escape_violations"][0]["file"] == "bad.py"
        assert data["passed"] is False

    def test_manifest_only_skips_lint(self, tmp_path: Path) -> None:
        """--manifest-only does not lint any source files."""
        pkg = self._pkg(tmp_path)
        # Escaping file present but --manifest-only → lint skipped
        (pkg / "bad.py").write_text("p = Path(__file__).parent.parent\n")
        with (
            patch("sys.argv", ["ll-verify-package-data", "-C", str(tmp_path), "--manifest-only"]),
            patch("little_loops.cli.verify_package_data.run_manifest_check", return_value=[]),
            patch("builtins.print"),
        ):
            assert main_verify_package_data() == 0

    def test_missing_assets_returns_one(self, tmp_path: Path) -> None:
        """Manifest check finding missing assets → exit 1."""
        pkg = self._pkg(tmp_path)
        (pkg / "ok.py").write_text("x = 1\n")
        with (
            patch("sys.argv", ["ll-verify-package-data", "-C", str(tmp_path)]),
            patch(
                "little_loops.cli.verify_package_data.run_manifest_check",
                return_value=[("assets", "missing.txt")],
            ),
            patch("builtins.print"),
        ):
            assert main_verify_package_data() == 1

    def test_allowlist_entries_cover_known_resolvers(self) -> None:
        """The allowlist includes both canonical resolver files."""
        assert "init/cli.py" in _ALLOWLIST
        assert "skill_expander.py" in _ALLOWLIST
