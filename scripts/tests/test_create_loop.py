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

from little_loops.fsm.validation import ValidationSeverity, load_and_validate, validate_fsm

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
    on_yes: done
    on_no: done
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
    on_yes: done
    on_no: fix-lint
  fix-lint:
    action: ruff check --fix src/
    on_yes: lint
    on_no: done
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
    on_yes: done
    on_no: fix
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
                "run": {"action": "pytest", "on_yes": "done", "on_no": "done"},
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
                    "run": {"action": "cmd", "on_yes": "done", "on_no": "done"},
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


# =============================================================================
# Harness Plan-Research-Implement-Report (Variant C) Structural Tests
# =============================================================================

HARNESS_PLAN_RESEARCH_IMPLEMENT_REPORT_YAML = """
name: harness-plan-research-implement-report
category: harness
description: |
  EXAMPLE: Specialist-role pipeline with Plan -> Research -> Implement -> Report decomposition.
initial: plan
max_iterations: 50
import:
  - lib/common.yaml
states:
  plan:
    action: "Create a detailed implementation plan."
    action_type: prompt
    capture: plan
    next: research
  research:
    action: "Research the codebase and documentation relevant to the plan."
    action_type: prompt
    capture: research
    next: implement
  implement:
    action: "Implement the plan using the research findings."
    action_type: prompt
    capture: execute_result
    max_retries: 3
    on_retry_exhausted: report
    next: check_stall
  check_stall:
    action: "echo checking stall"
    action_type: shell
    fragment: diff_stall_gate
    on_yes: check_concrete
    on_no: report
    on_error: report
  check_concrete:
    action: "pytest"
    action_type: shell
    evaluate:
      type: exit_code
    on_yes: check_semantic
    on_no: implement
    on_error: implement
  check_semantic:
    action: "echo Evaluating implementation quality"
    action_type: shell
    evaluate:
      type: llm_structured
      source: "${captured.execute_result.output}"
      prompt: "Evaluate the implementation. Answer YES or NO."
    on_yes: check_invariants
    on_no: implement
    on_partial: check_semantic
  check_invariants:
    action: "git diff --stat HEAD | wc -l | tr -d ' '"
    action_type: shell
    evaluate:
      type: output_numeric
      operator: lt
      target: 50
    on_yes: report
    on_no: implement
    on_error: report
  report:
    action: "Produce a completion report."
    action_type: prompt
    next: done
  done:
    terminal: true
"""


class TestHarnessPlanResearchImplementReport:
    """Structural validation for the Variant C scaffold from /ll:create-loop."""

    @pytest.fixture
    def scaffold(self) -> dict:
        return yaml.safe_load(HARNESS_PLAN_RESEARCH_IMPLEMENT_REPORT_YAML)

    def test_initial_state_is_plan(self, scaffold: dict) -> None:
        """Variant C must start from the plan state."""
        assert scaffold["initial"] == "plan"

    def test_required_states_exist(self, scaffold: dict) -> None:
        """All four specialist roles plus terminal state must be present."""
        states = set(scaffold["states"].keys())
        required = {"plan", "research", "implement", "report", "done"}
        assert required.issubset(states), f"Missing states: {required - states}"

    def test_phase_sequencing(self, scaffold: dict) -> None:
        """plan routes to research, research routes to implement."""
        states = scaffold["states"]
        assert states["plan"].get("next") == "research", "plan must route to research"
        assert states["research"].get("next") == "implement", "research must route to implement"

    def test_terminal_state(self, scaffold: dict) -> None:
        """done must be a terminal state."""
        assert scaffold["states"]["done"].get("terminal") is True

    def test_description_field(self, scaffold: dict) -> None:
        """Variant C scaffold must have a non-empty description."""
        assert scaffold.get("description"), "description field must be non-empty"


# =============================================================================
# Harness Variant A with Assumption Gate Tests (ENH-2215)
# =============================================================================

HARNESS_VARIANT_A_WITH_ASSUMPTION_GATE_YAML = """
name: harness-external-api
initial: assumption_gate
max_steps: 3
context:
  issue_file: ""
states:
  assumption_gate:
    loop: assumption-firewall
    with:
      input: "${context.issue_file}"
    on_success: execute
    on_failure: blocked
    on_error: blocked
  blocked:
    terminal: true
  execute:
    action: /ll:refine-issue --auto
    action_type: prompt
    timeout: 1500
    capture: execute_result
    next: done
  done:
    terminal: true
"""

HARNESS_VARIANT_A_NO_GATE_YAML = """
name: harness-refine-issue-no-gate
initial: execute
max_steps: 3
states:
  execute:
    action: /ll:refine-issue --auto
    action_type: prompt
    timeout: 1500
    capture: execute_result
    next: done
  done:
    terminal: true
"""


class TestHarnessVariantAWithAssumptionGate:
    """Structural tests for a harness with assumption-firewall gate (ENH-2215)."""

    @pytest.fixture
    def harness(self) -> dict:
        return yaml.safe_load(HARNESS_VARIANT_A_WITH_ASSUMPTION_GATE_YAML)

    def test_parses_as_yaml(self, harness: dict) -> None:
        assert isinstance(harness, dict)

    def test_initial_state_is_assumption_gate(self, harness: dict) -> None:
        assert harness.get("initial") == "assumption_gate"

    def test_assumption_gate_state_exists(self, harness: dict) -> None:
        assert "assumption_gate" in harness.get("states", {})

    def test_assumption_gate_uses_assumption_firewall_loop(self, harness: dict) -> None:
        gate = harness["states"]["assumption_gate"]
        assert gate.get("loop") == "assumption-firewall"

    def test_assumption_gate_with_input_is_context_issue_file(self, harness: dict) -> None:
        gate = harness["states"]["assumption_gate"]
        assert gate.get("with", {}).get("input") == "${context.issue_file}"

    def test_assumption_gate_routes_on_failure_to_blocked(self, harness: dict) -> None:
        gate = harness["states"]["assumption_gate"]
        assert gate.get("on_failure") == "blocked"

    def test_assumption_gate_routes_on_error_to_blocked(self, harness: dict) -> None:
        gate = harness["states"]["assumption_gate"]
        assert gate.get("on_error") == "blocked"

    def test_blocked_state_exists(self, harness: dict) -> None:
        assert "blocked" in harness.get("states", {})

    def test_blocked_state_is_terminal(self, harness: dict) -> None:
        assert harness["states"]["blocked"].get("terminal") is True

    def test_passes_fsm_validation(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        loops = tmp_path / ".loops"
        loops.mkdir()
        (loops / "harness-external-api.yaml").write_text(HARNESS_VARIANT_A_WITH_ASSUMPTION_GATE_YAML)
        monkeypatch.chdir(tmp_path)
        fsm, _ = load_and_validate(loops / "harness-external-api.yaml")
        errors = validate_fsm(fsm)
        hard_errors = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        assert not hard_errors, f"Assumption gate harness FSM errors: {[str(e) for e in hard_errors]}"


class TestHarnessVariantAWithoutAssumptionGate:
    """Regression: harnesses without external APIs must not include assumption_gate (ENH-2215)."""

    @pytest.fixture
    def harness(self) -> dict:
        return yaml.safe_load(HARNESS_VARIANT_A_NO_GATE_YAML)

    def test_initial_state_is_execute(self, harness: dict) -> None:
        assert harness.get("initial") == "execute"

    def test_no_assumption_gate_state(self, harness: dict) -> None:
        assert "assumption_gate" not in harness.get("states", {})

    def test_no_blocked_state(self, harness: dict) -> None:
        assert "blocked" not in harness.get("states", {})
