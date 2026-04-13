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
            "agent-eval-improve",
            "dataset-curation",
            "incremental-refactor",
            "prompt-across-issues",
            "prompt-regression-test",
            "test-coverage-improvement",
            "eval-driven-development",
            "greenfield-builder",
            "outer-loop-eval",
            "auto-refine-and-implement",
            "recursive-refine",
            "html-website-generator",
            "sprint-refine-and-implement",
            "svg-image-generator",
            "svg-textgrad",
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


class TestIssueRefinementSubLoop:
    """Tests that issue-refinement.yaml delegates refinement to the refine-to-ready-issue sub-loop."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "issue-refinement.yaml"
    REMOVED_STATES = [
        "route_format",
        "route_verify",
        "route_score",
        "format_issues",
        "score_issues",
        "refine_issues",
        "verify_only",
    ]

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_parse_id_capture_is_input(self, data: dict) -> None:
        """parse_id must capture as 'input' so context_passthrough injects it into child loop."""
        parse_id = data["states"].get("parse_id", {})
        assert parse_id.get("capture") == "input", (
            f"parse_id.capture should be 'input', got {parse_id.get('capture')!r} — "
            f"child loop reads context.input via context_passthrough"
        )

    def test_parse_id_routes_to_sub_loop(self, data: dict) -> None:
        """parse_id.on_yes must route to run_refine_to_ready, not route_format."""
        parse_id = data["states"].get("parse_id", {})
        assert parse_id.get("on_yes") == "run_refine_to_ready", (
            f"parse_id.on_yes should be 'run_refine_to_ready', got {parse_id.get('on_yes')!r}"
        )

    def test_run_refine_to_ready_state_exists(self, data: dict) -> None:
        """run_refine_to_ready sub-loop state must exist."""
        assert "run_refine_to_ready" in data["states"], (
            "State 'run_refine_to_ready' not found in issue-refinement.yaml"
        )

    def test_run_refine_to_ready_uses_sub_loop(self, data: dict) -> None:
        """run_refine_to_ready must use 'loop:' field to invoke refine-to-ready-issue."""
        state = data["states"].get("run_refine_to_ready", {})
        assert state.get("loop") == "refine-to-ready-issue", (
            f"run_refine_to_ready.loop should be 'refine-to-ready-issue', got {state.get('loop')!r}"
        )

    def test_run_refine_to_ready_has_context_passthrough(self, data: dict) -> None:
        """run_refine_to_ready must set context_passthrough: true to inject captured input."""
        state = data["states"].get("run_refine_to_ready", {})
        assert state.get("context_passthrough") is True, (
            f"run_refine_to_ready.context_passthrough should be true, got {state.get('context_passthrough')!r}"
        )

    def test_run_refine_to_ready_routes_to_check_commit(self, data: dict) -> None:
        """run_refine_to_ready on_yes must route to check_commit."""
        state = data["states"].get("run_refine_to_ready", {})
        assert state.get("on_yes") == "check_commit", (
            f"run_refine_to_ready.on_yes should be 'check_commit', got {state.get('on_yes')!r}"
        )

    def test_run_refine_to_ready_on_no_routes_to_handle_failure(self, data: dict) -> None:
        """run_refine_to_ready on_no must route to handle_failure for skip-list tracking."""
        state = data["states"].get("run_refine_to_ready", {})
        assert state.get("on_no") == "handle_failure", (
            f"run_refine_to_ready.on_no should be 'handle_failure', got {state.get('on_no')!r}"
        )

    def test_handle_failure_state_exists(self, data: dict) -> None:
        """handle_failure state must exist to track failed issues in skip list."""
        assert "handle_failure" in data["states"], (
            "State 'handle_failure' not found in issue-refinement.yaml"
        )

    def test_handle_failure_next_is_check_commit(self, data: dict) -> None:
        """handle_failure must route next to check_commit after appending to skip list."""
        state = data["states"].get("handle_failure", {})
        assert state.get("next") == "check_commit", (
            f"handle_failure.next should be 'check_commit', got {state.get('next')!r}"
        )

    def test_evaluate_action_includes_skip_list(self, data: dict) -> None:
        """evaluate action must pass skip list to ll-issues next-action."""
        evaluate = data["states"].get("evaluate", {})
        action = evaluate.get("action", "")
        assert "issue-refinement-skip-list" in action, (
            f"evaluate.action should reference issue-refinement-skip-list, got: {action!r}"
        )

    def test_init_action_clears_skip_list(self, data: dict) -> None:
        """init action must clear the skip list at the start of each run."""
        init = data["states"].get("init", {})
        action = init.get("action", "")
        assert "issue-refinement-skip-list" in action, (
            f"init.action should clear issue-refinement-skip-list, got: {action!r}"
        )

    @pytest.mark.parametrize("state_name", REMOVED_STATES)
    def test_removed_states_absent(self, data: dict, state_name: str) -> None:
        """Inline routing and prompt states must be removed — logic lives in refine-to-ready-issue."""
        assert state_name not in data["states"], (
            f"State '{state_name}' should have been removed; logic delegated to refine-to-ready-issue sub-loop"
        )


class TestRefineToReadyIssueSubLoop:
    """Tests that refine-to-ready-issue.yaml routes correctly through wire, breakdown, and confidence states."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "refine-to-ready-issue.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_confidence_check_routes_to_check_readiness(self, data: dict) -> None:
        """confidence_check must transition unconditionally to check_readiness (ENH-1033 split)."""
        confidence_check = data["states"].get("confidence_check", {})
        assert confidence_check.get("next") == "check_readiness", (
            f"confidence_check.next should be 'check_readiness', got {confidence_check.get('next')!r}"
        )

    def test_check_readiness_on_yes_routes_to_check_outcome(self, data: dict) -> None:
        """check_readiness.on_yes must route to check_outcome (readiness passed → check outcome next)."""
        state = data["states"].get("check_readiness", {})
        assert state.get("on_yes") == "check_outcome", (
            f"check_readiness.on_yes should be 'check_outcome', got {state.get('on_yes')!r}"
        )

    def test_check_readiness_on_no_routes_to_check_refine_limit(self, data: dict) -> None:
        """check_readiness.on_no must route to check_refine_limit (technical gap → retry refinement)."""
        state = data["states"].get("check_readiness", {})
        assert state.get("on_no") == "check_refine_limit", (
            f"check_readiness.on_no should be 'check_refine_limit', got {state.get('on_no')!r}"
        )

    def test_check_readiness_on_error_is_check_scores_from_file(self, data: dict) -> None:
        """check_readiness.on_error must route to check_scores_from_file (preserves error fallback)."""
        state = data["states"].get("check_readiness", {})
        assert state.get("on_error") == "check_scores_from_file", (
            f"check_readiness.on_error should be 'check_scores_from_file', got {state.get('on_error')!r}"
        )

    def test_check_outcome_on_yes_routes_to_done(self, data: dict) -> None:
        """check_outcome.on_yes must route to done (both scores pass)."""
        state = data["states"].get("check_outcome", {})
        assert state.get("on_yes") == "done", (
            f"check_outcome.on_yes should be 'done', got {state.get('on_yes')!r}"
        )

    def test_check_outcome_on_no_routes_to_breakdown_issue(self, data: dict) -> None:
        """check_outcome.on_no must route to breakdown_issue (outcome-only fail → scope reduction, not retry)."""
        state = data["states"].get("check_outcome", {})
        assert state.get("on_no") == "breakdown_issue", (
            f"check_outcome.on_no should be 'breakdown_issue', got {state.get('on_no')!r}"
        )

    def test_check_scores_from_file_state_exists(self, data: dict) -> None:
        """check_scores_from_file state must exist as the error recovery path for confidence_check."""
        assert "check_scores_from_file" in data["states"], (
            "State 'check_scores_from_file' not found in refine-to-ready-issue.yaml — "
            "required as fallback when confidence_check LLM evaluation times out"
        )

    def test_check_scores_from_file_routes_to_done(self, data: dict) -> None:
        """check_scores_from_file.on_yes must route to done when scores meet thresholds."""
        state = data["states"].get("check_scores_from_file", {})
        assert state.get("on_yes") == "done", (
            f"check_scores_from_file.on_yes should be 'done', got {state.get('on_yes')!r}"
        )

    def test_check_scores_from_file_routes_to_breakdown_issue_on_no(self, data: dict) -> None:
        """check_scores_from_file.on_no must route to breakdown_issue (ENH-1033: outcome-only fails avoid retry)."""
        state = data["states"].get("check_scores_from_file", {})
        assert state.get("on_no") == "breakdown_issue", (
            f"check_scores_from_file.on_no should be 'breakdown_issue', got {state.get('on_no')!r}"
        )

    def test_verify_issue_state_absent(self, data: dict) -> None:
        """verify_issue state must not exist — it was removed in ENH-980."""
        assert "verify_issue" not in data["states"], (
            "State 'verify_issue' should have been removed; confidence_check.on_yes now routes to 'done'"
        )

    def test_check_lifetime_limit_routes_to_breakdown_issue(self, data: dict) -> None:
        """check_lifetime_limit.on_no must route to breakdown_issue (not failed)."""
        state = data["states"].get("check_lifetime_limit", {})
        assert state.get("on_no") == "breakdown_issue", (
            f"check_lifetime_limit.on_no should be 'breakdown_issue', got {state.get('on_no')!r}"
        )

    def test_breakdown_issue_state_exists(self, data: dict) -> None:
        """breakdown_issue state must exist to invoke /ll:issue-size-review on cap exhaustion."""
        assert "breakdown_issue" in data["states"], (
            "State 'breakdown_issue' not found in refine-to-ready-issue.yaml"
        )

    def test_breakdown_issue_is_slash_command(self, data: dict) -> None:
        """breakdown_issue must use action_type: slash_command."""
        state = data["states"].get("breakdown_issue", {})
        assert state.get("action_type") == "slash_command", (
            f"breakdown_issue.action_type should be 'slash_command', got {state.get('action_type')!r}"
        )

    def test_breakdown_issue_action_contains_auto(self, data: dict) -> None:
        """breakdown_issue action must include --auto to avoid blocking on interactive input."""
        state = data["states"].get("breakdown_issue", {})
        assert "--auto" in state.get("action", ""), (
            "breakdown_issue action must include '--auto' flag to prevent interactive stalling"
        )

    def test_breakdown_issue_routes_to_write_broke_down(self, data: dict) -> None:
        """breakdown_issue.next must be 'write_broke_down' to set the flag before exiting."""
        state = data["states"].get("breakdown_issue", {})
        assert state.get("next") == "write_broke_down", (
            f"breakdown_issue.next should be 'write_broke_down', got {state.get('next')!r}"
        )

    def test_write_broke_down_state_exists(self, data: dict) -> None:
        """write_broke_down state must exist to signal to recursive-refine that breakdown ran."""
        assert "write_broke_down" in data["states"], (
            "State 'write_broke_down' not found in refine-to-ready-issue.yaml"
        )

    def test_write_broke_down_routes_to_done(self, data: dict) -> None:
        """write_broke_down.next must route to done."""
        state = data["states"].get("write_broke_down", {})
        assert state.get("next") == "done", (
            f"write_broke_down.next should be 'done', got {state.get('next')!r}"
        )

    def test_write_broke_down_action_writes_flag(self, data: dict) -> None:
        """write_broke_down action must write to the recursive-refine-broke-down flag file."""
        state = data["states"].get("write_broke_down", {})
        assert "recursive-refine-broke-down" in state.get("action", ""), (
            "write_broke_down action must write to '.loops/tmp/recursive-refine-broke-down'"
        )

    def test_broke_down_flag_initialized_in_resolve_issue(self, data: dict) -> None:
        """resolve_issue action must initialize the recursive-refine-broke-down flag file."""
        state = data["states"].get("resolve_issue", {})
        assert "recursive-refine-broke-down" in state.get("action", ""), (
            "resolve_issue action must initialize '.loops/tmp/recursive-refine-broke-down' flag"
        )

    def test_breakdown_issue_on_error_is_failed(self, data: dict) -> None:
        """breakdown_issue.on_error must route to 'failed'."""
        state = data["states"].get("breakdown_issue", {})
        assert state.get("on_error") == "failed", (
            f"breakdown_issue.on_error should be 'failed', got {state.get('on_error')!r}"
        )

    def test_check_wire_done_state_exists(self, data: dict) -> None:
        """check_wire_done state must exist to gate wire_issue to once per run."""
        assert "check_wire_done" in data["states"], (
            "State 'check_wire_done' not found in refine-to-ready-issue.yaml"
        )

    def test_check_wire_done_evaluate_output_numeric_lt_1(self, data: dict) -> None:
        """check_wire_done must use output_numeric lt 1 to detect whether wire has run."""
        state = data["states"].get("check_wire_done", {})
        evaluate = state.get("evaluate", {})
        assert evaluate.get("type") == "output_numeric", (
            f"check_wire_done evaluate.type should be 'output_numeric', got {evaluate.get('type')!r}"
        )
        assert evaluate.get("operator") == "lt", (
            f"check_wire_done evaluate.operator should be 'lt', got {evaluate.get('operator')!r}"
        )
        assert evaluate.get("target") == 1, (
            f"check_wire_done evaluate.target should be 1, got {evaluate.get('target')!r}"
        )

    def test_wire_issue_state_exists(self, data: dict) -> None:
        """wire_issue state must exist to run /ll:wire-issue once per loop run."""
        assert "wire_issue" in data["states"], (
            "State 'wire_issue' not found in refine-to-ready-issue.yaml"
        )

    def test_wire_issue_action_contains_auto(self, data: dict) -> None:
        """wire_issue action must include --auto to avoid blocking on interactive input."""
        state = data["states"].get("wire_issue", {})
        assert "--auto" in state.get("action", ""), (
            "wire_issue action must include '--auto' flag to prevent interactive stalling"
        )

    def test_wire_issue_on_error_is_confidence_check(self, data: dict) -> None:
        """wire_issue.on_error must route to confidence_check (wiring failure is non-fatal)."""
        state = data["states"].get("wire_issue", {})
        assert state.get("on_error") == "confidence_check", (
            f"wire_issue.on_error should be 'confidence_check', got {state.get('on_error')!r}"
        )

    def test_mark_wire_done_state_exists(self, data: dict) -> None:
        """mark_wire_done state must exist to set the wire-done flag after wiring."""
        assert "mark_wire_done" in data["states"], (
            "State 'mark_wire_done' not found in refine-to-ready-issue.yaml"
        )

    def test_mark_wire_done_routes_to_confidence_check(self, data: dict) -> None:
        """mark_wire_done.next must route to confidence_check."""
        state = data["states"].get("mark_wire_done", {})
        assert state.get("next") == "confidence_check", (
            f"mark_wire_done.next should be 'confidence_check', got {state.get('next')!r}"
        )

    def test_wire_done_flag_initialized_in_resolve_issue(self, data: dict) -> None:
        """resolve_issue action must initialize the wire-done flag file."""
        state = data["states"].get("resolve_issue", {})
        assert "refine-to-ready-wire-done" in state.get("action", ""), (
            "resolve_issue action must initialize '.loops/tmp/refine-to-ready-wire-done' flag"
        )

    def test_check_refine_limit_routes_to_refine_issue(self, data: dict) -> None:
        """check_refine_limit.on_yes must route directly to refine_issue (not check_lifetime_limit)."""
        state = data["states"].get("check_refine_limit", {})
        assert state.get("on_yes") == "refine_issue", (
            f"check_refine_limit.on_yes should be 'refine_issue', got {state.get('on_yes')!r}"
        )

    def test_check_refine_limit_on_no_routes_to_breakdown_issue(self, data: dict) -> None:
        """check_refine_limit.on_no must route to breakdown_issue (not failed)."""
        state = data["states"].get("check_refine_limit", {})
        assert state.get("on_no") == "breakdown_issue", (
            f"check_refine_limit.on_no should be 'breakdown_issue', got {state.get('on_no')!r}"
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


class TestPromptAcrossIssuesLoop:
    """Structural tests for the prompt-across-issues FSM loop."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "prompt-across-issues.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_required_top_level_fields(self, data: dict) -> None:
        """Loop must have name, initial, and states fields."""
        assert data.get("name") == "prompt-across-issues"
        assert data.get("initial") == "init"
        assert isinstance(data.get("states"), dict)

    def test_required_states_exist(self, data: dict) -> None:
        """All required states must be present."""
        required = {"init", "discover", "prepare_prompt", "execute", "advance", "done", "error"}
        actual = set(data["states"].keys())
        missing = required - actual
        assert not missing, f"Missing states: {missing}"

    def test_done_state_is_terminal(self, data: dict) -> None:
        """done state must have terminal: true."""
        done_state = data["states"].get("done", {})
        assert done_state.get("terminal") is True

    def test_error_state_is_terminal(self, data: dict) -> None:
        """error state must have terminal: true."""
        error_state = data["states"].get("error", {})
        assert error_state.get("terminal") is True

    def test_discover_captures_current_item(self, data: dict) -> None:
        """discover state must capture as 'current_item'."""
        discover_state = data["states"].get("discover", {})
        assert discover_state.get("capture") == "current_item"

    def test_prepare_prompt_captures_final_prompt(self, data: dict) -> None:
        """prepare_prompt state must capture as 'final_prompt'."""
        prepare_state = data["states"].get("prepare_prompt", {})
        assert prepare_state.get("capture") == "final_prompt"

    def test_execute_uses_final_prompt(self, data: dict) -> None:
        """execute state action must reference ${captured.final_prompt.output}."""
        execute_state = data["states"].get("execute", {})
        action = execute_state.get("action", "")
        assert "${captured.final_prompt.output}" in action

    def test_advance_removes_from_pending_file(self, data: dict) -> None:
        """advance state action must modify the pending.txt file."""
        advance_state = data["states"].get("advance", {})
        action = advance_state.get("action", "")
        assert "pending" in action

    def test_init_validates_input(self, data: dict) -> None:
        """init state action must check that ${context.input} is non-empty."""
        init_state = data["states"].get("init", {})
        action = init_state.get("action", "")
        assert "${context.input}" in action

    def test_execute_has_max_retries(self, data: dict) -> None:
        """execute state must define max_retries to prevent stuck items."""
        execute_state = data["states"].get("execute", {})
        assert execute_state.get("max_retries", 0) > 0


class TestAutoRefineAndImplementLoop:
    """Structural tests for the auto-refine-and-implement FSM loop."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "auto-refine-and-implement.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_required_top_level_fields(self, data: dict) -> None:
        """Loop must have name, initial, and states fields."""
        assert data.get("name") == "auto-refine-and-implement"
        assert data.get("initial") == "init"
        assert isinstance(data.get("states"), dict)

    def test_required_states_exist(self, data: dict) -> None:
        """All required states must be present."""
        required = {
            "init",
            "get_next_issue",
            "refine_issue",
            "get_passed_issues",
            "implement_next",
            "implement_issue",
            "skip_and_continue",
            "done",
        }
        actual = set(data["states"].keys())
        missing = required - actual
        assert not missing, f"Missing states: {missing}"

    def test_init_state_exists(self, data: dict) -> None:
        """init state must exist to clear temp files on each fresh run."""
        assert "init" in data["states"], "init state missing from auto-refine-and-implement"

    def test_init_state_is_shell_type(self, data: dict) -> None:
        """init state must be a shell action with unconditional next: get_next_issue."""
        init = data["states"].get("init", {})
        assert init.get("action_type") == "shell"
        assert init.get("next") == "get_next_issue"

    def test_init_clears_skip_file(self, data: dict) -> None:
        """init action must clear the skip file so each run starts fresh."""
        init = data["states"].get("init", {})
        action = init.get("action", "")
        assert "auto-refine-and-implement-skipped.txt" in action, (
            f"init.action should clear auto-refine-and-implement-skipped.txt, got: {action!r}"
        )

    def test_init_clears_impl_queue_file(self, data: dict) -> None:
        """init action must clear the impl queue so each run starts fresh."""
        init = data["states"].get("init", {})
        action = init.get("action", "")
        assert "auto-refine-and-implement-impl-queue.txt" in action, (
            f"init.action should clear auto-refine-and-implement-impl-queue.txt, got: {action!r}"
        )

    def test_done_state_is_terminal(self, data: dict) -> None:
        """done state must have terminal: true."""
        done_state = data["states"].get("done", {})
        assert done_state.get("terminal") is True

    def test_get_next_issue_captures_input(self, data: dict) -> None:
        """get_next_issue must capture as 'input' for context_passthrough to work."""
        state = data["states"].get("get_next_issue", {})
        assert state.get("capture") == "input"

    def test_refine_issue_delegates_to_recursive_refine(self, data: dict) -> None:
        """refine_issue must delegate to recursive-refine with context_passthrough."""
        state = data["states"].get("refine_issue", {})
        assert state.get("loop") == "recursive-refine"
        assert state.get("context_passthrough") is True

    def test_refine_issue_has_success_and_failure_routes(self, data: dict) -> None:
        """refine_issue must define on_success and on_failure routes."""
        state = data["states"].get("refine_issue", {})
        assert state.get("on_success") == "get_passed_issues"
        assert state.get("on_failure") == "skip_and_continue"

    def test_implement_next_captures_impl_id(self, data: dict) -> None:
        """implement_next must capture as 'impl_id' for implement_issue to reference."""
        state = data["states"].get("implement_next", {})
        assert state.get("capture") == "impl_id"

    def test_implement_issue_uses_impl_id(self, data: dict) -> None:
        """implement_issue action must reference captured.impl_id.output."""
        state = data["states"].get("implement_issue", {})
        action = state.get("action", "")
        assert "${captured.impl_id.output}" in action

    def test_implement_issue_routes_to_implement_next(self, data: dict) -> None:
        """implement_issue must loop back to implement_next to drain the queue."""
        state = data["states"].get("implement_issue", {})
        assert state.get("next") == "implement_next"

    def test_skip_and_continue_uses_input_capture(self, data: dict) -> None:
        """skip_and_continue must reference captured.input.output (not impl_id)."""
        state = data["states"].get("skip_and_continue", {})
        action = state.get("action", "")
        assert "${captured.input.output}" in action

    def test_skip_and_continue_routes_to_get_next_issue(self, data: dict) -> None:
        """skip_and_continue must route back to get_next_issue."""
        state = data["states"].get("skip_and_continue", {})
        assert state.get("next") == "get_next_issue"

    def test_skipped_file_uses_loops_tmp(self, data: dict) -> None:
        """Skipped tracking file must use .loops/tmp/ path."""
        states = data.get("states", {})
        skipped_ref = "auto-refine-and-implement-skipped"
        found = False
        for state_data in states.values():
            action = state_data.get("action", "")
            if skipped_ref in action:
                found = True
                assert ".loops/tmp/" in action
        assert found, f"No state references {skipped_ref!r}"

    def test_impl_queue_file_uses_loops_tmp(self, data: dict) -> None:
        """Impl queue file must use .loops/tmp/ path."""
        states = data.get("states", {})
        queue_ref = "auto-refine-and-implement-impl-queue"
        found = False
        for state_data in states.values():
            action = state_data.get("action", "")
            if queue_ref in action:
                found = True
                assert ".loops/tmp/" in action
        assert found, f"No state references {queue_ref!r}"

    def test_get_passed_issues_reads_recursive_refine_outputs(self, data: dict) -> None:
        """get_passed_issues must read both recursive-refine output files."""
        state = data["states"].get("get_passed_issues", {})
        action = state.get("action", "")
        assert "recursive-refine-passed.txt" in action
        assert "recursive-refine-skipped.txt" in action


class TestRecursiveRefineLoop:
    """Structural tests for the recursive-refine FSM loop."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "recursive-refine.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_required_top_level_fields(self, data: dict) -> None:
        """Loop must have name, initial, and states fields."""
        assert data.get("name") == "recursive-refine"
        assert data.get("initial") == "parse_input"
        assert isinstance(data.get("states"), dict)

    def test_required_states_exist(self, data: dict) -> None:
        """All required states must be present."""
        required = {
            "parse_input",
            "dequeue_next",
            "capture_baseline",
            "run_refine",
            "check_passed",
            "detect_children",
            "enqueue_children",
            "size_review_snap",
            "check_broke_down",
            "recheck_scores",
            "run_size_review",
            "enqueue_or_skip",
            "done",
            "failed",
        }
        actual = set(data["states"].keys())
        missing = required - actual
        assert not missing, f"Missing states: {missing}"

    def test_done_state_is_terminal(self, data: dict) -> None:
        """done state must have terminal: true."""
        done_state = data["states"].get("done", {})
        assert done_state.get("terminal") is True

    def test_failed_state_is_terminal(self, data: dict) -> None:
        """failed state must have terminal: true."""
        failed_state = data["states"].get("failed", {})
        assert failed_state.get("terminal") is True

    def test_dequeue_next_captures_input(self, data: dict) -> None:
        """dequeue_next must capture as 'input' for context_passthrough to work."""
        state = data["states"].get("dequeue_next", {})
        assert state.get("capture") == "input"

    def test_run_refine_delegates_to_sub_loop(self, data: dict) -> None:
        """run_refine must delegate to refine-to-ready-issue with context_passthrough."""
        state = data["states"].get("run_refine", {})
        assert state.get("loop") == "refine-to-ready-issue"
        assert state.get("context_passthrough") is True

    def test_run_refine_has_success_and_failure_routes(self, data: dict) -> None:
        """run_refine must define on_success and on_failure routes."""
        state = data["states"].get("run_refine", {})
        assert "on_success" in state
        assert "on_failure" in state

    def test_queue_file_uses_loops_tmp(self, data: dict) -> None:
        """Queue file references must use .loops/tmp/ (not bare /tmp/)."""
        states = data.get("states", {})
        queue_ref = "recursive-refine-queue"
        found = False
        for state_data in states.values():
            action = state_data.get("action", "")
            if queue_ref in action:
                found = True
                assert ".loops/tmp/" in action, (
                    f"Queue file reference must use .loops/tmp/, got: {action[:200]}"
                )
        assert found, f"No state references {queue_ref!r}"

    def test_skipped_file_uses_loops_tmp(self, data: dict) -> None:
        """Skipped tracking file must use .loops/tmp/ path."""
        states = data.get("states", {})
        skipped_ref = "recursive-refine-skipped"
        found = False
        for state_data in states.values():
            action = state_data.get("action", "")
            if skipped_ref in action:
                found = True
                assert ".loops/tmp/" in action
        assert found, f"No state references {skipped_ref!r}"

    def test_parse_input_validates_context_input(self, data: dict) -> None:
        """parse_input must check that ${context.input} is non-empty."""
        state = data["states"].get("parse_input", {})
        action = state.get("action", "")
        assert "${context.input}" in action

    def test_run_size_review_uses_auto_flag(self, data: dict) -> None:
        """run_size_review must invoke issue-size-review with --auto flag."""
        state = data["states"].get("run_size_review", {})
        action = state.get("action", "")
        assert "issue-size-review" in action
        assert "--auto" in action

    def test_context_thresholds_defined(self, data: dict) -> None:
        """context block must define the three threshold/limit variables."""
        ctx = data.get("context", {})
        assert "readiness_threshold" in ctx
        assert "outcome_threshold" in ctx
        assert "max_refine_count" in ctx

    def test_size_review_snap_routes_to_check_broke_down(self, data: dict) -> None:
        """size_review_snap.next must route to check_broke_down to guard against duplicate size-review."""
        state = data["states"].get("size_review_snap", {})
        assert state.get("next") == "check_broke_down", (
            f"size_review_snap.next should be 'check_broke_down', got {state.get('next')!r}"
        )

    def test_check_broke_down_state_exists(self, data: dict) -> None:
        """check_broke_down state must exist to skip duplicate size-review after breakdown_issue."""
        assert "check_broke_down" in data["states"], (
            "State 'check_broke_down' not found in recursive-refine.yaml"
        )

    def test_check_broke_down_evaluate_output_numeric_lt_1(self, data: dict) -> None:
        """check_broke_down must use output_numeric lt 1 to detect whether breakdown_issue ran."""
        state = data["states"].get("check_broke_down", {})
        evaluate = state.get("evaluate", {})
        assert evaluate.get("type") == "output_numeric", (
            f"check_broke_down evaluate.type should be 'output_numeric', got {evaluate.get('type')!r}"
        )
        assert evaluate.get("operator") == "lt", (
            f"check_broke_down evaluate.operator should be 'lt', got {evaluate.get('operator')!r}"
        )
        assert evaluate.get("target") == 1, (
            f"check_broke_down evaluate.target should be 1, got {evaluate.get('target')!r}"
        )

    def test_check_broke_down_on_yes_routes_to_recheck_scores(self, data: dict) -> None:
        """check_broke_down.on_yes (flag=0, not broken down) must route to recheck_scores."""
        state = data["states"].get("check_broke_down", {})
        assert state.get("on_yes") == "recheck_scores", (
            f"check_broke_down.on_yes should be 'recheck_scores', got {state.get('on_yes')!r}"
        )

    def test_check_broke_down_on_no_routes_to_enqueue_or_skip(self, data: dict) -> None:
        """check_broke_down.on_no (flag=1, already broken down) must route to enqueue_or_skip."""
        state = data["states"].get("check_broke_down", {})
        assert state.get("on_no") == "enqueue_or_skip", (
            f"check_broke_down.on_no should be 'enqueue_or_skip', got {state.get('on_no')!r}"
        )

    def test_check_broke_down_on_error_routes_to_recheck_scores(self, data: dict) -> None:
        """check_broke_down.on_error must route to recheck_scores (fail-safe: treat as not broken down)."""
        state = data["states"].get("check_broke_down", {})
        assert state.get("on_error") == "recheck_scores", (
            f"check_broke_down.on_error should be 'recheck_scores', got {state.get('on_error')!r}"
        )

    def test_broke_down_flag_cleared_in_capture_baseline(self, data: dict) -> None:
        """capture_baseline must clear recursive-refine-broke-down so each issue iteration starts clean."""
        state = data["states"].get("capture_baseline", {})
        assert "recursive-refine-broke-down" in state.get("action", ""), (
            "capture_baseline action must clear '.loops/tmp/recursive-refine-broke-down' flag"
        )

    def test_recheck_scores_routes_to_dequeue_next(self, data: dict) -> None:
        """recheck_scores.on_yes must route to dequeue_next when scores already pass."""
        state = data["states"].get("recheck_scores", {})
        assert state.get("on_yes") == "dequeue_next", (
            f"recheck_scores.on_yes should be 'dequeue_next', got {state.get('on_yes')!r}"
        )

    def test_recheck_scores_on_no_routes_to_run_size_review(self, data: dict) -> None:
        """recheck_scores.on_no must route to run_size_review when scores do not pass."""
        state = data["states"].get("recheck_scores", {})
        assert state.get("on_no") == "run_size_review", (
            f"recheck_scores.on_no should be 'run_size_review', got {state.get('on_no')!r}"
        )

    def test_recheck_scores_on_error_routes_to_run_size_review(self, data: dict) -> None:
        """recheck_scores.on_error must route to run_size_review on evaluation error."""
        state = data["states"].get("recheck_scores", {})
        assert state.get("on_error") == "run_size_review", (
            f"recheck_scores.on_error should be 'run_size_review', got {state.get('on_error')!r}"
        )

    def test_detect_children_filters_by_parent_reference(self, data: dict) -> None:
        """detect_children must use diff-ids.txt intermediate and filter by Decomposed from."""
        state = data["states"].get("detect_children", {})
        action = state.get("action", "")
        assert "recursive-refine-diff-ids.txt" in action, (
            "detect_children must write comm output to diff-ids.txt before filtering"
        )
        assert "Decomposed from" in action, (
            "detect_children must filter candidates by 'Decomposed from' parent reference"
        )

    def test_enqueue_or_skip_filters_by_parent_reference(self, data: dict) -> None:
        """enqueue_or_skip must use diff-ids.txt intermediate and filter by Decomposed from."""
        state = data["states"].get("enqueue_or_skip", {})
        action = state.get("action", "")
        assert "recursive-refine-diff-ids.txt" in action, (
            "enqueue_or_skip must write comm output to diff-ids.txt before filtering"
        )
        assert "Decomposed from" in action, (
            "enqueue_or_skip must filter candidates by 'Decomposed from' parent reference"
        )

    def test_enqueue_children_moves_parent_to_completed(self, data: dict) -> None:
        """enqueue_children must find and move the parent file to .issues/completed/ after decomposition."""
        state = data["states"].get("enqueue_children", {})
        action = state.get("action", "")
        assert "find .issues" in action, (
            "enqueue_children must use 'find .issues' to locate the parent file"
        )
        assert "completed" in action, (
            "enqueue_children must reference 'completed' directory for the move"
        )
        assert "mv" in action, (
            "enqueue_children must contain 'mv' to move the parent file"
        )

    def test_enqueue_or_skip_moves_parent_to_completed_when_children_found(self, data: dict) -> None:
        """enqueue_or_skip children-found branch must find and move the parent file to .issues/completed/."""
        state = data["states"].get("enqueue_or_skip", {})
        action = state.get("action", "")
        # The find+mv block must appear before the 'else' (no-children branch)
        children_branch = action.split("else")[0] if "else" in action else action
        assert "find .issues" in children_branch, (
            "enqueue_or_skip children-found branch must use 'find .issues' to locate the parent file"
        )
        assert "completed" in children_branch, (
            "enqueue_or_skip children-found branch must reference 'completed' directory"
        )
        assert "mv" in children_branch, (
            "enqueue_or_skip children-found branch must contain 'mv' to move the parent file"
        )

    def test_enqueue_or_skip_else_does_not_move_parent(self, data: dict) -> None:
        """enqueue_or_skip else branch (no children) must NOT move the parent to completed/."""
        state = data["states"].get("enqueue_or_skip", {})
        action = state.get("action", "")
        assert "else" in action, "enqueue_or_skip must have an else branch"
        else_branch = action.split("else", 1)[1]
        assert "completed" not in else_branch, (
            "enqueue_or_skip else branch must NOT move parent to completed/ — "
            "issue remains open for future retry"
        )


class TestSprintBuildAndValidateLoop:
    """Structural tests for the sprint-build-and-validate FSM loop."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "sprint-build-and-validate.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_required_top_level_fields(self, data: dict) -> None:
        """Loop must have name, initial, and states fields."""
        assert data.get("name") == "sprint-build-and-validate"
        assert data.get("initial") == "create_sprint"
        assert isinstance(data.get("states"), dict)

    def test_required_states_exist(self, data: dict) -> None:
        """All required states must be present."""
        required = {
            "create_sprint",
            "route_create",
            "size_review",
            "map_dependencies",
            "audit_conflicts",
            "verify_issues",
            "route_validation",
            "commit",
            "run_sprint",
            "extract_unresolved",
            "refine_unresolved",
            "fix_issues",
            "done",
        }
        actual = set(data["states"].keys())
        missing = required - actual
        assert not missing, f"Missing states: {missing}"

    def test_route_review_removed(self, data: dict) -> None:
        """route_review state must not exist (replaced by shell_exit routing on run_sprint)."""
        assert "route_review" not in data.get("states", {}), (
            "route_review is a dead state and must be removed"
        )

    def test_route_create_on_yes_targets_size_review(self, data: dict) -> None:
        """route_create.on_yes must target size_review (not map_dependencies)."""
        state = data["states"].get("route_create", {})
        assert state.get("on_yes") == "size_review", (
            f"route_create.on_yes should be 'size_review', got {state.get('on_yes')!r}"
        )

    def test_size_review_next_targets_map_dependencies(self, data: dict) -> None:
        """size_review.next must route to map_dependencies."""
        state = data["states"].get("size_review", {})
        assert state.get("next") == "map_dependencies", (
            f"size_review.next should be 'map_dependencies', got {state.get('next')!r}"
        )

    def test_run_sprint_uses_shell_exit_fragment(self, data: dict) -> None:
        """run_sprint must use fragment: shell_exit for exit-code-based routing."""
        state = data["states"].get("run_sprint", {})
        assert state.get("fragment") == "shell_exit", (
            f"run_sprint.fragment should be 'shell_exit', got {state.get('fragment')!r}"
        )

    def test_run_sprint_on_yes_routes_to_done(self, data: dict) -> None:
        """run_sprint.on_yes (exit 0) must route to done."""
        state = data["states"].get("run_sprint", {})
        assert state.get("on_yes") == "done", (
            f"run_sprint.on_yes should be 'done', got {state.get('on_yes')!r}"
        )

    def test_run_sprint_on_no_routes_to_extract_unresolved(self, data: dict) -> None:
        """run_sprint.on_no (non-zero exit) must route to extract_unresolved."""
        state = data["states"].get("run_sprint", {})
        assert state.get("on_no") == "extract_unresolved", (
            f"run_sprint.on_no should be 'extract_unresolved', got {state.get('on_no')!r}"
        )

    def test_extract_unresolved_captures_as_input(self, data: dict) -> None:
        """extract_unresolved must capture as 'input' for context_passthrough to work."""
        state = data["states"].get("extract_unresolved", {})
        assert state.get("capture") == "input", (
            f"extract_unresolved.capture should be 'input', got {state.get('capture')!r}"
        )

    def test_extract_unresolved_on_yes_routes_to_refine_unresolved(self, data: dict) -> None:
        """extract_unresolved.on_yes must route to refine_unresolved."""
        state = data["states"].get("extract_unresolved", {})
        assert state.get("on_yes") == "refine_unresolved", (
            f"extract_unresolved.on_yes should be 'refine_unresolved', got {state.get('on_yes')!r}"
        )

    def test_extract_unresolved_on_no_routes_to_done(self, data: dict) -> None:
        """extract_unresolved.on_no (no unresolved issues) must route to done."""
        state = data["states"].get("extract_unresolved", {})
        assert state.get("on_no") == "done", (
            f"extract_unresolved.on_no should be 'done', got {state.get('on_no')!r}"
        )

    def test_refine_unresolved_delegates_to_recursive_refine(self, data: dict) -> None:
        """refine_unresolved must delegate to recursive-refine sub-loop."""
        state = data["states"].get("refine_unresolved", {})
        assert state.get("loop") == "recursive-refine", (
            f"refine_unresolved.loop should be 'recursive-refine', got {state.get('loop')!r}"
        )

    def test_refine_unresolved_uses_context_passthrough(self, data: dict) -> None:
        """refine_unresolved must use context_passthrough to pass captured.input to child loop."""
        state = data["states"].get("refine_unresolved", {})
        assert state.get("context_passthrough") is True, (
            "refine_unresolved must have context_passthrough: true"
        )

    def test_done_state_is_terminal(self, data: dict) -> None:
        """done state must have terminal: true."""
        done_state = data["states"].get("done", {})
        assert done_state.get("terminal") is True


class TestHtmlWebsiteGeneratorLoop:
    """Structural tests for the html-website-generator FSM loop."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "html-website-generator.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_required_top_level_fields(self, data: dict) -> None:
        """Loop must have name, initial, input_key, and states fields."""
        assert data.get("name") == "html-website-generator"
        assert data.get("initial") == "plan"
        assert data.get("input_key") == "description"
        assert isinstance(data.get("states"), dict)

    def test_required_states_exist(self, data: dict) -> None:
        """All required states must be present."""
        required = {"plan", "generate", "evaluate", "score", "done"}
        actual = set(data["states"].keys())
        missing = required - actual
        assert not missing, f"Missing states: {missing}"

    def test_done_state_is_terminal(self, data: dict) -> None:
        """done state must have terminal: true."""
        done_state = data["states"].get("done", {})
        assert done_state.get("terminal") is True

    def test_evaluate_state_is_shell(self, data: dict) -> None:
        """evaluate state must use action_type: shell for the Playwright CLI call."""
        state = data["states"].get("evaluate", {})
        assert state.get("action_type") == "shell"

    def test_evaluate_state_has_output_contains_evaluator(self, data: dict) -> None:
        """evaluate state must have an output_contains evaluator with pattern CAPTURED."""
        state = data["states"].get("evaluate", {})
        evaluator = state.get("evaluate", {})
        assert evaluator.get("type") == "output_contains"
        assert evaluator.get("pattern") == "CAPTURED"

    def test_evaluate_routes_to_score_on_yes(self, data: dict) -> None:
        """evaluate state must route to score when screenshot succeeds."""
        state = data["states"].get("evaluate", {})
        assert state.get("on_yes") == "score"

    def test_evaluate_routes_to_generate_on_no(self, data: dict) -> None:
        """evaluate state must route back to generate when screenshot fails."""
        state = data["states"].get("evaluate", {})
        assert state.get("on_no") == "generate"

    def test_score_state_routes_to_done_on_pass(self, data: dict) -> None:
        """score state must route to done when all criteria pass."""
        state = data["states"].get("score", {})
        assert state.get("on_yes") == "done"

    def test_score_state_routes_to_generate_on_iterate(self, data: dict) -> None:
        """score state must route back to generate when criteria are not met."""
        state = data["states"].get("score", {})
        assert state.get("on_no") == "generate"

    def test_context_has_description_and_output_dir(self, data: dict) -> None:
        """context block must define description and output_dir variables."""
        ctx = data.get("context", {})
        assert "description" in ctx
        assert "output_dir" in ctx

    def test_max_iterations_and_timeout_defined(self, data: dict) -> None:
        """Loop must define max_iterations and timeout."""
        assert data.get("max_iterations", 0) > 0
        assert data.get("timeout", 0) > 0


class TestSvgImageGeneratorLoop:
    """Structural tests for the svg-image-generator FSM loop."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "svg-image-generator.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_required_top_level_fields(self, data: dict) -> None:
        """Loop must have name, initial, input_key, and states fields."""
        assert data.get("name") == "svg-image-generator"
        assert data.get("initial") == "init"
        assert data.get("input_key") == "description"
        assert isinstance(data.get("states"), dict)

    def test_required_states_exist(self, data: dict) -> None:
        """All required states must be present."""
        required = {"init", "plan", "generate", "evaluate", "score", "done"}
        actual = set(data["states"].keys())
        missing = required - actual
        assert not missing, f"Missing states: {missing}"

    def test_init_state_is_shell_with_capture(self, data: dict) -> None:
        """init state must be a shell action that captures the timestamped run directory."""
        state = data["states"].get("init", {})
        assert state.get("action_type") == "shell"
        assert state.get("capture") == "run_dir"
        assert state.get("next") == "plan"

    def test_done_state_is_terminal(self, data: dict) -> None:
        """done state must have terminal: true."""
        done_state = data["states"].get("done", {})
        assert done_state.get("terminal") is True

    def test_evaluate_state_is_shell(self, data: dict) -> None:
        """evaluate state must use action_type: shell for the Playwright CLI call."""
        state = data["states"].get("evaluate", {})
        assert state.get("action_type") == "shell"

    def test_evaluate_state_has_output_contains_evaluator(self, data: dict) -> None:
        """evaluate state must have an output_contains evaluator with pattern CAPTURED."""
        state = data["states"].get("evaluate", {})
        evaluator = state.get("evaluate", {})
        assert evaluator.get("type") == "output_contains"
        assert evaluator.get("pattern") == "CAPTURED"

    def test_evaluate_routes_to_score_on_yes(self, data: dict) -> None:
        """evaluate state must route to score when screenshot succeeds."""
        state = data["states"].get("evaluate", {})
        assert state.get("on_yes") == "score"

    def test_evaluate_routes_to_generate_on_no(self, data: dict) -> None:
        """evaluate state must route back to generate when screenshot fails."""
        state = data["states"].get("evaluate", {})
        assert state.get("on_no") == "generate"

    def test_score_state_routes_to_done_on_pass(self, data: dict) -> None:
        """score state must route to done when all criteria pass."""
        state = data["states"].get("score", {})
        assert state.get("on_yes") == "done"

    def test_score_state_routes_to_generate_on_iterate(self, data: dict) -> None:
        """score state must route back to generate when criteria are not met."""
        state = data["states"].get("score", {})
        assert state.get("on_no") == "generate"

    def test_context_has_description_and_output_dir(self, data: dict) -> None:
        """context block must define description and output_dir variables with correct defaults."""
        ctx = data.get("context", {})
        assert "description" in ctx
        assert ctx.get("output_dir") == ".loops/tmp/svg-image-generator"

    def test_max_iterations_and_timeout_defined(self, data: dict) -> None:
        """Loop must define max_iterations and timeout."""
        assert data.get("max_iterations", 0) > 0
        assert data.get("timeout", 0) > 0


class TestSvgTextgradLoop:
    """Structural tests for the svg-textgrad FSM loop."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "svg-textgrad.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_required_top_level_fields(self, data: dict) -> None:
        """Loop must have name, initial, input_key, and states fields."""
        assert data.get("name") == "svg-textgrad"
        assert data.get("initial") == "init"
        assert data.get("input_key") == "description"
        assert isinstance(data.get("states"), dict)

    def test_required_states_exist(self, data: dict) -> None:
        """All required states must be present."""
        required = {
            "init", "plan", "generate", "evaluate", "score",
            "compute_gradient", "append_gradient", "apply_gradient", "done",
        }
        actual = set(data["states"].keys())
        missing = required - actual
        assert not missing, f"Missing states: {missing}"

    def test_init_state_is_shell_with_capture(self, data: dict) -> None:
        """init state must be a shell action that captures the timestamped run directory."""
        state = data["states"].get("init", {})
        assert state.get("action_type") == "shell"
        assert state.get("capture") == "run_dir"
        assert state.get("next") == "plan"

    def test_done_state_is_terminal(self, data: dict) -> None:
        """done state must have terminal: true."""
        done_state = data["states"].get("done", {})
        assert done_state.get("terminal") is True

    def test_generate_does_not_reference_critique(self, data: dict) -> None:
        """generate state must NOT reference critique.md (reads only brief.md)."""
        state = data["states"].get("generate", {})
        action = state.get("action", "")
        assert "critique" not in action, "generate state must not reference critique.md"

    def test_score_state_routes_to_done_on_pass(self, data: dict) -> None:
        """score state must route to done when all criteria pass."""
        state = data["states"].get("score", {})
        assert state.get("on_yes") == "done"

    def test_score_state_routes_to_compute_gradient_on_iterate(self, data: dict) -> None:
        """score state must route to compute_gradient (not generate) on ITERATE."""
        state = data["states"].get("score", {})
        assert state.get("on_no") == "compute_gradient"

    def test_compute_gradient_captures_gradient(self, data: dict) -> None:
        """compute_gradient state must capture its output as 'gradient' and route to append_gradient."""
        state = data["states"].get("compute_gradient", {})
        assert state.get("capture") == "gradient"
        assert state.get("next") == "append_gradient"

    def test_append_gradient_is_shell_routes_to_apply_gradient(self, data: dict) -> None:
        """append_gradient state must be a shell state that routes to apply_gradient."""
        state = data["states"].get("append_gradient", {})
        assert state.get("action_type") == "shell"
        assert state.get("next") == "apply_gradient"

    def test_apply_gradient_routes_to_generate(self, data: dict) -> None:
        """apply_gradient state must route back to generate."""
        state = data["states"].get("apply_gradient", {})
        assert state.get("next") == "generate"

    def test_context_has_description_and_output_dir(self, data: dict) -> None:
        """context block must define description and output_dir with correct defaults."""
        ctx = data.get("context", {})
        assert "description" in ctx
        assert ctx.get("output_dir") == ".loops/tmp/svg-textgrad"

    def test_max_iterations_and_timeout_defined(self, data: dict) -> None:
        """Loop must define max_iterations and timeout."""
        assert data.get("max_iterations", 0) > 0
        assert data.get("timeout", 0) > 0
