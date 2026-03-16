"""Tests for built-in loops shipped with the plugin."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from little_loops.fsm.validation import ValidationSeverity, load_and_validate, validate_fsm

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

    def test_all_validate_as_valid_fsm(self, builtin_loops: list[Path]) -> None:
        """All built-in loops load and validate as FSMs without errors."""
        for loop_file in builtin_loops:
            fsm, _ = load_and_validate(loop_file)
            errors = validate_fsm(fsm)
            error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]
            assert not error_list, (
                f"{loop_file.name}: validation errors: {[str(e) for e in error_list]}"
            )

    def test_expected_loops_exist(self) -> None:
        """The expected set of built-in loops exists."""
        expected = {
            "dead-code-cleanup",
            "docs-sync",
            "fix-quality-and-tests",
            "issue-discovery-triage",
            "issue-refinement",
            "issue-size-split",
            "issue-staleness-review",
            "backlog-flow-optimizer",
            "sprint-build-and-validate",
            "worktree-health",
            "rl-bandit",
            "rl-rlhf",
            "rl-policy",
        }
        actual = {f.stem for f in BUILTIN_LOOPS_DIR.glob("*.yaml")}
        assert expected == actual


class TestBuiltinLoopResolution:
    """Tests for resolve_loop_path with built-in fallback."""

    def test_builtin_fallback(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """resolve_loop_path falls back to built-in loops."""
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "validate", "fix-quality-and-tests"]):
            from little_loops.cli import main_loop

            result = main_loop()
        # Should succeed because fix-quality-and-tests is a built-in
        assert result == 0

    def test_project_overrides_builtin(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Project-local loop takes priority over built-in."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        # Create a project-local loop with the same name but different content
        (loops_dir / "fix-quality-and-tests.yaml").write_text(
            "name: fix-quality-and-tests\ninitial: start\nstates:\n  start:\n    terminal: true\n"
        )

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "validate", "fix-quality-and-tests"]):
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
        assert "fix-quality-and-tests" in captured.out

    def test_list_hides_overridden_builtin(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Project loop with same name hides built-in from list."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "fix-quality-and-tests.yaml").write_text("name: fix-quality-and-tests")

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "list"]):
            from little_loops.cli import main_loop

            result = main_loop()
        assert result == 0
        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")
        # fix-quality-and-tests should appear without [built-in] tag (project version)
        pr_lines = [line for line in lines if "fix-quality-and-tests" in line]
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
        with patch.object(sys, "argv", ["ll-loop", "install", "fix-quality-and-tests"]):
            from little_loops.cli import main_loop

            result = main_loop()
        assert result == 0
        dest = tmp_path / ".loops" / "fix-quality-and-tests.yaml"
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
        with patch.object(sys, "argv", ["ll-loop", "install", "issue-refinement"]):
            from little_loops.cli import main_loop

            result = main_loop()
        assert result == 0
        assert (tmp_path / ".loops" / "issue-refinement.yaml").exists()

    def test_install_rejects_existing(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """install refuses to overwrite existing project loop."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "fix-quality-and-tests.yaml").write_text("existing content")

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "install", "fix-quality-and-tests"]):
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


class TestBuiltinLoopScratchIsolation:
    """Tests that built-in loops use project-scoped scratch paths, not global /tmp names."""

    AFFECTED_LOOPS = [
        "issue-refinement",
        "fix-quality-and-tests",
        "dead-code-cleanup",
    ]

    # Bare /tmp paths that must not appear in any action text
    FORBIDDEN_PATTERNS = [
        "/tmp/issue-refinement-commit-count",
        "/tmp/ll-test-results.txt",
        "/tmp/ll-dead-code-report.txt",
        "/tmp/ll-dead-code-excluded.txt",
        "/tmp/ll-dead-code-tests.txt",
        "/tmp/ll-pr-test-results.txt",
    ]

    def _collect_action_text(self, data: dict) -> list[str]:
        """Recursively collect all action strings from an FSM data dict."""
        texts: list[str] = []
        for state_data in data.get("states", {}).values():
            action = state_data.get("action", "")
            if isinstance(action, str):
                texts.append(action)
        return texts

    @pytest.mark.parametrize("loop_name", AFFECTED_LOOPS)
    def test_no_global_tmp_paths(self, loop_name: str) -> None:
        """Action text in affected loops must not reference bare /tmp scratch paths."""
        loop_file = BUILTIN_LOOPS_DIR / f"{loop_name}.yaml"
        assert loop_file.exists(), f"Loop file not found: {loop_file}"
        data = yaml.safe_load(loop_file.read_text())
        action_texts = self._collect_action_text(data)
        combined = "\n".join(action_texts)
        for forbidden in self.FORBIDDEN_PATTERNS:
            # Use negative lookbehind so ".loops/tmp/foo" does not trigger a
            # false positive when checking for the bare "/tmp/foo" pattern.
            bare_pattern = r"(?<!\.loops)" + re.escape(forbidden)
            assert not re.search(bare_pattern, combined), (
                f"{loop_name}.yaml still references global tmp path: {forbidden!r}"
            )


class TestBuiltinLoopOnBlockedCoverage:
    """Tests that llm_structured evaluate states in built-in loops define on_blocked handlers."""

    # Each entry: (loop_file, state_name, expected_on_blocked_value)
    REQUIRED_ON_BLOCKED: list[tuple[str, str, str]] = [
        ("sprint-build-and-validate.yaml", "route_validation", "fix_issues"),
        ("sprint-build-and-validate.yaml", "route_review", "fix_issues"),
        ("issue-staleness-review.yaml", "triage", "find_stale"),
        ("issue-size-split.yaml", "route_large", "done"),
    ]

    @pytest.mark.parametrize("loop_file,state_name,expected", REQUIRED_ON_BLOCKED)
    def test_llm_structured_state_has_on_blocked(
        self, loop_file: str, state_name: str, expected: str
    ) -> None:
        """Each audited llm_structured evaluate state must define on_blocked."""
        path = BUILTIN_LOOPS_DIR / loop_file
        assert path.exists(), f"Loop file not found: {path}"
        data = yaml.safe_load(path.read_text())
        state_data = data.get("states", {}).get(state_name)
        assert state_data is not None, f"State '{state_name}' not found in {loop_file}"
        assert state_data.get("evaluate", {}).get("type") == "llm_structured", (
            f"State '{state_name}' in {loop_file} is not an llm_structured evaluate state"
        )
        assert "on_blocked" in state_data, (
            f"State '{state_name}' in {loop_file} is missing on_blocked handler"
        )
        assert state_data["on_blocked"] == expected, (
            f"State '{state_name}' in {loop_file}: expected on_blocked={expected!r}, "
            f"got {state_data['on_blocked']!r}"
        )
