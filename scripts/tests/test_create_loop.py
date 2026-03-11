"""Tests for /ll:create-loop skill artifacts.

Since /ll:create-loop is a prompt-based skill (markdown instructions for Claude),
we cannot directly unit test the interactive wizard flow. Instead, we test:

1. Example YAML patterns from the command documentation are valid
2. CLI validation works on generated loop files
3. File creation in .loops/ directory structure
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

# =============================================================================
# CLI Validation Tests
# =============================================================================


class TestLoopFileValidation:
    """Tests for loop file creation and validation via CLI."""

    @pytest.fixture
    def loops_dir(self, tmp_path: Path) -> Path:
        """Create a .loops directory."""
        loops = tmp_path / ".loops"
        loops.mkdir()
        return loops

    def test_valid_goal_loop_file(self, loops_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Valid FSM loop file (goal-style) passes ll-loop validate."""
        loop_content = """
name: test-goal
initial: run
states:
  run:
    action: pytest
    on_success: done
    on_failure: done
  done:
    terminal: true
max_iterations: 10
"""
        (loops_dir / "test-goal.yaml").write_text(loop_content)
        monkeypatch.chdir(loops_dir.parent)

        with patch.object(sys, "argv", ["ll-loop", "validate", "test-goal"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0

    def test_valid_invariants_loop_file(
        self, loops_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Valid FSM loop file (invariants-style) passes ll-loop validate."""
        loop_content = """
name: quality-gate
initial: lint
states:
  lint:
    action: ruff check src/
    on_success: done
    on_failure: fix-lint
  fix-lint:
    action: ruff check --fix src/
    on_success: lint
    on_failure: done
  done:
    terminal: true
max_iterations: 20
"""
        (loops_dir / "quality-gate.yaml").write_text(loop_content)
        monkeypatch.chdir(loops_dir.parent)

        with patch.object(sys, "argv", ["ll-loop", "validate", "quality-gate"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0

    def test_valid_convergence_loop_file(
        self, loops_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Valid FSM loop file (convergence-style) passes ll-loop validate."""
        loop_content = """
name: reduce-errors
initial: check
states:
  check:
    action: "echo 5"
    on_success: done
    on_failure: fix
  fix:
    action: echo fix
    next: check
  done:
    terminal: true
max_iterations: 20
"""
        (loops_dir / "reduce-errors.yaml").write_text(loop_content)
        monkeypatch.chdir(loops_dir.parent)

        with patch.object(sys, "argv", ["ll-loop", "validate", "reduce-errors"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0

    def test_valid_imperative_loop_file(
        self, loops_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Valid FSM loop file (imperative-style) passes ll-loop validate."""
        loop_content = """
name: build-test
initial: build
states:
  build:
    action: echo build
    next: test
  test:
    action: echo test
    next: done
  done:
    terminal: true
max_iterations: 10
"""
        (loops_dir / "build-test.yaml").write_text(loop_content)
        monkeypatch.chdir(loops_dir.parent)

        with patch.object(sys, "argv", ["ll-loop", "validate", "build-test"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0

    def test_invalid_loop_file_fails_validation(
        self, loops_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Invalid FSM loop file fails ll-loop validate."""
        loop_content = """
name: bad-goal
initial: nonexistent
states:
  start:
    terminal: true
# initial references nonexistent state = validation error
"""
        (loops_dir / "bad-goal.yaml").write_text(loop_content)
        monkeypatch.chdir(loops_dir.parent)

        with patch.object(sys, "argv", ["ll-loop", "validate", "bad-goal"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 1
        captured = capsys.readouterr()
        # Error should mention the issue
        output = captured.err.lower() + captured.out.lower()
        assert "invalid" in output or "nonexistent" in output or "bad-goal" in output


# =============================================================================
# File Creation Tests
# =============================================================================


class TestLoopFileCreation:
    """Tests for loop file creation in .loops/ directory."""

    def test_loops_directory_creation(self, tmp_path: Path) -> None:
        """Loop file can be created after .loops/ directory exists."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        loop_content = {
            "name": "test-loop",
            "initial": "run",
            "states": {
                "run": {"action": "pytest", "on_success": "done", "on_failure": "done"},
                "done": {"terminal": True},
            },
        }

        loop_file = loops_dir / "test-loop.yaml"
        loop_file.write_text(yaml.dump(loop_content))

        assert loop_file.exists()
        loaded = yaml.safe_load(loop_file.read_text())
        assert loaded["name"] == "test-loop"

    def test_loop_file_naming_convention(self, tmp_path: Path) -> None:
        """Loop files use name.yaml naming convention."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        loop_names = ["fix-types", "quality-guardian", "reduce-errors", "build-test-check"]

        for name in loop_names:
            loop_content = {
                "name": name,
                "initial": "run",
                "states": {
                    "run": {"action": "cmd", "on_success": "done", "on_failure": "done"},
                    "done": {"terminal": True},
                },
            }
            loop_file = loops_dir / f"{name}.yaml"
            loop_file.write_text(yaml.dump(loop_content))

            assert loop_file.exists()
            loaded = yaml.safe_load(loop_file.read_text())
            assert loaded["name"] == name

    def test_existing_file_detection(self, tmp_path: Path) -> None:
        """Existing loop file can be detected before overwrite."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        loop_file = loops_dir / "existing-loop.yaml"
        loop_file.write_text("name: existing-loop")

        # Simulate the check from create-loop/SKILL.md Step 5
        exists = loop_file.exists()
        assert exists is True
