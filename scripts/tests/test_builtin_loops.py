"""Tests for built-in loops shipped with the plugin."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from little_loops.fsm.compilers import compile_paradigm
from little_loops.fsm.validation import ValidationSeverity, validate_fsm

BUILTIN_LOOPS_DIR = Path(__file__).parent.parent.parent / "loops"


class TestBuiltinLoopFiles:
    """Tests that all built-in loop YAML files are valid."""

    @pytest.fixture
    def builtin_loops(self) -> list[Path]:
        """Get all built-in loop files."""
        assert BUILTIN_LOOPS_DIR.exists(), f"Built-in loops dir not found: {BUILTIN_LOOPS_DIR}"
        files = sorted(BUILTIN_LOOPS_DIR.glob("*.yaml"))
        assert len(files) > 0, "No built-in loop files found"
        return files

    def test_all_parse_as_yaml(self, builtin_loops: list[Path]) -> None:
        """All built-in loop files parse as valid YAML."""
        for loop_file in builtin_loops:
            with open(loop_file) as f:
                data = yaml.safe_load(f)
            assert isinstance(data, dict), f"{loop_file.name}: root must be a mapping"

    def test_all_have_required_paradigm_fields(self, builtin_loops: list[Path]) -> None:
        """All built-in loops have paradigm and name fields."""
        for loop_file in builtin_loops:
            with open(loop_file) as f:
                data = yaml.safe_load(f)
            assert "paradigm" in data, f"{loop_file.name}: missing 'paradigm'"
            assert "name" in data, f"{loop_file.name}: missing 'name'"
            assert data["name"] == loop_file.stem, (
                f"{loop_file.name}: name '{data['name']}' doesn't match filename stem"
            )

    def test_all_compile_to_valid_fsm(self, builtin_loops: list[Path]) -> None:
        """All built-in loops compile to valid FSMs without errors."""
        for loop_file in builtin_loops:
            with open(loop_file) as f:
                spec = yaml.safe_load(f)
            fsm = compile_paradigm(spec)
            errors = validate_fsm(fsm)
            error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]
            assert not error_list, (
                f"{loop_file.name}: validation errors: {[str(e) for e in error_list]}"
            )

    def test_expected_loops_exist(self) -> None:
        """The expected set of built-in loops exists."""
        expected = {
            "issue-readiness-cycle",
            "pre-pr-checks",
            "issue-verification",
            "codebase-scan",
            "quality-gate",
        }
        actual = {f.stem for f in BUILTIN_LOOPS_DIR.glob("*.yaml")}
        assert expected == actual


class TestBuiltinLoopResolution:
    """Tests for resolve_loop_path with built-in fallback."""

    def test_builtin_fallback(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """resolve_loop_path falls back to built-in loops."""
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "validate", "pre-pr-checks"]):
            from little_loops.cli import main_loop

            result = main_loop()
        # Should succeed because pre-pr-checks is a built-in
        assert result == 0

    def test_project_overrides_builtin(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Project-local loop takes priority over built-in."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        # Create a project-local loop with the same name but different content
        (loops_dir / "pre-pr-checks.yaml").write_text(
            "name: pre-pr-checks\ninitial: start\nstates:\n  start:\n    terminal: true\n"
        )

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "validate", "pre-pr-checks"]):
            from little_loops.cli import main_loop

            result = main_loop()
        # Should use the project-local version (which is a simple terminal FSM)
        assert result == 0


class TestBuiltinLoopList:
    """Tests for ll-loop list with built-in loops."""

    def test_list_shows_builtin_tag(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """ll-loop list shows [built-in] tag for bundled loops."""
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "list"]):
            from little_loops.cli import main_loop

            result = main_loop()
        assert result == 0
        captured = capsys.readouterr()
        assert "[built-in]" in captured.out
        assert "pre-pr-checks" in captured.out

    def test_list_hides_overridden_builtin(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Project loop with same name hides built-in from list."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "pre-pr-checks.yaml").write_text("name: pre-pr-checks")

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "list"]):
            from little_loops.cli import main_loop

            result = main_loop()
        assert result == 0
        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")
        # pre-pr-checks should appear without [built-in] tag (project version)
        pr_lines = [line for line in lines if "pre-pr-checks" in line]
        assert len(pr_lines) == 1
        assert "[built-in]" not in pr_lines[0]


class TestBuiltinLoopInstall:
    """Tests for ll-loop install subcommand."""

    def test_install_copies_to_project(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """install copies built-in loop to .loops/."""
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "install", "pre-pr-checks"]):
            from little_loops.cli import main_loop

            result = main_loop()
        assert result == 0
        dest = tmp_path / ".loops" / "pre-pr-checks.yaml"
        assert dest.exists()
        captured = capsys.readouterr()
        assert "Installed" in captured.out

    def test_install_creates_loops_dir(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """install creates .loops/ directory if it doesn't exist."""
        monkeypatch.chdir(tmp_path)
        assert not (tmp_path / ".loops").exists()
        with patch.object(sys, "argv", ["ll-loop", "install", "quality-gate"]):
            from little_loops.cli import main_loop

            result = main_loop()
        assert result == 0
        assert (tmp_path / ".loops" / "quality-gate.yaml").exists()

    def test_install_rejects_existing(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """install refuses to overwrite existing project loop."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "pre-pr-checks.yaml").write_text("existing content")

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "install", "pre-pr-checks"]):
            from little_loops.cli import main_loop

            result = main_loop()
        assert result == 1

    def test_install_rejects_unknown(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """install rejects unknown loop name."""
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "install", "nonexistent-loop"]):
            from little_loops.cli import main_loop

            result = main_loop()
        assert result == 1
