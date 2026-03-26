"""Tests for built-in loops shipped with the plugin."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from little_loops.fsm.validation import ValidationSeverity, load_and_validate, validate_fsm

BUILTIN_LOOPS_DIR = Path(__file__).parent.parent / "little_loops" / "loops"


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
            "evaluation-quality",
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
            "rl-coding-agent",
            "apo-feedback-refinement",
            "apo-contrastive",
            "apo-opro",
            "apo-beam",
            "apo-textgrad",
            "examples-miner",
            "context-health-monitor",
            "harness-single-shot",
            "harness-multi-item",
            "general-task",
            "refine-to-ready-issue",
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


class TestEvaluationQualityLoop:
    """Structural tests for the evaluation-quality FSM loop."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "evaluation-quality.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_required_top_level_fields(self, data: dict) -> None:
        """Loop must have name, initial, and states fields."""
        assert data.get("name") == "evaluation-quality"
        assert data.get("initial") == "sample"
        assert isinstance(data.get("states"), dict)

    def test_required_states_exist(self, data: dict) -> None:
        """All required states must be present."""
        required = {
            "sample",
            "evaluate_code",
            "score",
            "route_action",
            "route_issues",
            "route_code",
            "remediate_issues",
            "remediate_code",
            "remediate_backlog",
            "prepare_report",
            "report",
            "done",
        }
        actual = set(data["states"].keys())
        missing = required - actual
        assert not missing, f"Missing states: {missing}"

    def test_done_state_is_terminal(self, data: dict) -> None:
        """done state must have terminal: true."""
        done_state = data["states"].get("done", {})
        assert done_state.get("terminal") is True

    def test_score_state_has_capture(self, data: dict) -> None:
        """score state must define capture: scores so route states can interpolate it."""
        score_state = data["states"].get("score", {})
        assert score_state.get("capture") == "scores"

    def test_route_states_have_on_error(self, data: dict) -> None:
        """All route/evaluate states must define on_error to prevent hangs."""
        route_states = ["route_action", "route_issues", "route_code"]
        for state_name in route_states:
            state = data["states"].get(state_name, {})
            assert "on_error" in state, f"Route state '{state_name}' missing on_error"

    def test_context_thresholds_defined(self, data: dict) -> None:
        """context block must define the three quality thresholds."""
        ctx = data.get("context", {})
        assert "issue_quality_threshold" in ctx
        assert "code_health_threshold" in ctx
        assert "backlog_health_threshold" in ctx

    def test_evaluate_code_uses_loops_tmp(self, data: dict) -> None:
        """evaluate_code state must use .loops/tmp/ paths, not bare /tmp/."""
        action = data["states"].get("evaluate_code", {}).get("action", "")
        assert ".loops/tmp/" in action, "evaluate_code must use .loops/tmp/ for output files"
        # Bare /tmp/... references are forbidden; .loops/tmp/... is fine.
        # Use negative lookbehind to avoid false positives on ".loops/tmp/eval-..."
        assert not re.search(r"(?<!\.loops)/tmp/eval-", action), (
            "evaluate_code must not use bare /tmp/ paths"
        )

    def test_prepare_report_is_shell_state(self, data: dict) -> None:
        """prepare_report must be a shell state (date expansion needs shell context)."""
        state = data["states"].get("prepare_report", {})
        assert state.get("action_type") == "shell"

    def test_report_references_captured_report_path(self, data: dict) -> None:
        """report state must reference ${captured.report_path.output} for dated filename."""
        action = data["states"].get("report", {}).get("action", "")
        assert "${captured.report_path.output}" in action

    def test_score_state_emits_primary_concern(self, data: dict) -> None:
        """score state prompt must instruct output of PRIMARY_CONCERN tag."""
        action = data["states"].get("score", {}).get("action", "")
        assert "PRIMARY_CONCERN" in action

    def test_route_action_routes_on_none(self, data: dict) -> None:
        """route_action must route to prepare_report when PRIMARY_CONCERN: NONE.

        prepare_report is required in all paths (including the healthy/NONE path)
        because $(date +%Y-%m-%d) does not expand in prompt states — a shell state
        must compute the dated report path before the report prompt state runs.
        """
        state = data["states"].get("route_action", {})
        assert state.get("on_yes") == "prepare_report"
        evaluate = state.get("evaluate", {})
        assert "NONE" in evaluate.get("pattern", "")

    def test_max_iterations_and_timeout(self, data: dict) -> None:
        """Loop must define max_iterations and timeout."""
        assert data.get("max_iterations", 0) > 0
        assert data.get("timeout", 0) > 0


class TestIssueRefinementLoopOnError:
    """Tests that prompt states in issue-refinement.yaml define on_error handlers."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "issue-refinement.yaml"
    PROMPT_STATES_REQUIRING_ON_ERROR = ["format_issues", "score_issues", "refine_issues"]

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    @pytest.mark.parametrize("state_name", PROMPT_STATES_REQUIRING_ON_ERROR)
    def test_prompt_state_has_on_error(self, data: dict, state_name: str) -> None:
        """Each prompt state must define on_error to prevent loop termination on SIGKILL."""
        state = data["states"].get(state_name)
        assert state is not None, f"State '{state_name}' not found"
        assert state.get("action_type") == "prompt", f"State '{state_name}' is not a prompt state"
        assert "on_error" in state, (
            f"Prompt state '{state_name}' missing on_error handler — "
            f"SIGKILL will terminate the loop instead of recovering"
        )

    @pytest.mark.parametrize("state_name", PROMPT_STATES_REQUIRING_ON_ERROR)
    def test_prompt_state_on_error_routes_to_check_commit(
        self, data: dict, state_name: str
    ) -> None:
        """on_error for each prompt state must route to check_commit."""
        state = data["states"].get(state_name, {})
        assert state.get("on_error") == "check_commit", (
            f"Prompt state '{state_name}' on_error should be 'check_commit', "
            f"got {state.get('on_error')!r}"
        )


class TestHarnessCapture:
    """Tests that harness YAML files wire execute output to check_semantic via capture/source."""

    HARNESS_FILES = [
        "harness-single-shot.yaml",
        "harness-multi-item.yaml",
    ]

    @pytest.mark.parametrize("loop_name", HARNESS_FILES)
    def test_execute_state_has_capture_execute_result(self, loop_name: str) -> None:
        """execute state must define capture: execute_result so check_semantic can reference it."""
        path = BUILTIN_LOOPS_DIR / loop_name
        assert path.exists(), f"Loop file not found: {path}"
        data = yaml.safe_load(path.read_text())
        execute_state = data.get("states", {}).get("execute", {})
        assert execute_state.get("capture") == "execute_result", (
            f"{loop_name}: execute state must have 'capture: execute_result' so "
            f"check_semantic can reference the skill output via ${{captured.execute_result.output}}"
        )

    @pytest.mark.parametrize("loop_name", HARNESS_FILES)
    def test_check_semantic_evaluate_has_source(self, loop_name: str) -> None:
        """check_semantic evaluate block must define source pointing to execute's captured output."""
        path = BUILTIN_LOOPS_DIR / loop_name
        assert path.exists(), f"Loop file not found: {path}"
        data = yaml.safe_load(path.read_text())
        check_semantic = data.get("states", {}).get("check_semantic", {})
        evaluate = check_semantic.get("evaluate", {})
        assert evaluate.get("source") == "${captured.execute_result.output}", (
            f"{loop_name}: check_semantic.evaluate must have "
            f"'source: \"${{captured.execute_result.output}}\"' so the LLM evaluator "
            f"receives actual skill output as evidence, not the echo string"
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
