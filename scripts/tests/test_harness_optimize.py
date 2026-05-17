"""Tests for the harness-optimize built-in loop."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from little_loops.fsm.validation import ValidationSeverity, load_and_validate, validate_fsm
from little_loops.loops.yaml_state_editor import extract_action, replace_action

BUILTIN_LOOPS_DIR = Path(__file__).parent.parent / "little_loops" / "loops"
LOOP_FILE = BUILTIN_LOOPS_DIR / "harness-optimize.yaml"


@pytest.fixture
def loop_data() -> dict:
    """Load the harness-optimize YAML."""
    assert LOOP_FILE.exists(), f"harness-optimize.yaml not found at {LOOP_FILE}"
    with open(LOOP_FILE) as f:
        return yaml.safe_load(f)


class TestHarnessOptimizeFile:
    """Tests that harness-optimize.yaml exists and is structurally valid."""

    def test_file_exists(self) -> None:
        assert LOOP_FILE.exists(), f"harness-optimize.yaml not found at {LOOP_FILE}"

    def test_parses_as_yaml(self, loop_data: dict) -> None:
        assert isinstance(loop_data, dict), "root must be a mapping"

    def test_validates_as_fsm(self) -> None:
        fsm, _ = load_and_validate(LOOP_FILE)
        errors = validate_fsm(fsm)
        error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        assert not error_list, f"FSM validation errors: {[str(e) for e in error_list]}"

    def test_name(self, loop_data: dict) -> None:
        assert loop_data.get("name") == "harness-optimize"

    def test_initial_state(self, loop_data: dict) -> None:
        assert loop_data.get("initial") == "init_run"

    def test_terminal_state(self, loop_data: dict) -> None:
        states = loop_data.get("states", {})
        assert "done" in states
        assert states["done"].get("terminal") is True

    def test_context_defaults(self, loop_data: dict) -> None:
        context = loop_data.get("context", {})
        assert "targets" in context, "context must have targets"
        assert context.get("targets") == "", "targets default must be empty string"
        assert "tasks_dir" in context, "context must have tasks_dir"
        assert context.get("tasks_dir") == "", "tasks_dir default must be empty string"
        assert "scorer" in context, "context must have scorer"
        assert context.get("scorer") == "", "scorer default must be empty string"
        assert context.get("target_score") == 1.0, "target_score default must be 1.0"
        assert context.get("max_iterations") == 30, "max_iterations default must be 30"


class TestHarnessOptimizeStates:
    """Tests for required states and their structure."""

    REQUIRED_STATES = {
        "init_run",
        "load_directive",
        "baseline_score",
        "init_prev",
        "propose",
        "apply",
        "score",
        "gate",
        "commit_and_log",
        "revert_and_log",
        "write_trajectory_accepted",
        "write_trajectory_rejected",
        "capture_prev",
        "done",
    }

    def test_has_all_required_states(self, loop_data: dict) -> None:
        actual = set(loop_data.get("states", {}).keys())
        missing = self.REQUIRED_STATES - actual
        assert not missing, f"Missing required states: {missing}"

    def test_baseline_score_uses_run_benchmark_fragment(self, loop_data: dict) -> None:
        state = loop_data["states"]["baseline_score"]
        assert state.get("fragment") == "run_benchmark"
        assert state.get("capture") == "baseline"
        assert "context.scorer" in state.get("action", "")
        assert "context.tasks_dir" in state.get("action", "")
        assert state.get("on_yes") == "init_prev"
        assert state.get("on_no") == "done"
        assert state.get("on_error") == "done"

    def test_init_prev_captures_prev_score(self, loop_data: dict) -> None:
        state = loop_data["states"]["init_prev"]
        assert state.get("capture") == "prev_score"
        assert state.get("next") == "propose"

    def test_score_state_uses_run_benchmark_fragment(self, loop_data: dict) -> None:
        state = loop_data["states"]["score"]
        assert state.get("fragment") == "run_benchmark"
        assert state.get("capture") == "benchmark_score"
        assert "context.scorer" in state.get("action", "")
        assert "context.tasks_dir" in state.get("action", "")
        assert state.get("on_yes") == "gate"
        assert state.get("on_no") == "revert_and_log"
        assert state.get("on_error") == "revert_and_log"

    def test_gate_has_convergence_evaluator(self, loop_data: dict) -> None:
        evaluate = loop_data["states"]["gate"].get("evaluate", {})
        assert evaluate.get("type") == "convergence"
        assert evaluate.get("direction") == "maximize"
        assert "previous" in evaluate, (
            "gate evaluate must have previous field (prevents always-progress bug on iteration 1)"
        )
        assert "target" in evaluate
        assert "tolerance" in evaluate

    def test_gate_routes_correctly(self, loop_data: dict) -> None:
        state = loop_data["states"]["gate"]
        route = state.get("route", {})
        assert route.get("stall") == "revert_and_log"
        assert route.get("error") == "revert_and_log"
        assert route.get("target") == "commit_and_log"
        assert route.get("progress") == "commit_and_log"

    def test_revert_uses_scoped_targets(self, loop_data: dict) -> None:
        action = loop_data["states"]["revert_and_log"].get("action", "")
        assert "context.targets" in action, (
            "revert_and_log must scope revert to ${context.targets}, not bare 'git checkout -- .'"
        )

    def test_capture_prev_captures_prev_score(self, loop_data: dict) -> None:
        state = loop_data["states"]["capture_prev"]
        assert state.get("capture") == "prev_score"
        assert state.get("next") == "propose"

    def test_write_trajectory_accepted_routes_to_capture_prev(self, loop_data: dict) -> None:
        assert loop_data["states"]["write_trajectory_accepted"].get("next") == "capture_prev"

    def test_write_trajectory_rejected_routes_to_done(self, loop_data: dict) -> None:
        assert loop_data["states"]["write_trajectory_rejected"].get("next") == "done"

    def test_trajectory_path_in_accepted_state(self, loop_data: dict) -> None:
        action = loop_data["states"]["write_trajectory_accepted"].get("action", "")
        assert "captured.traj_path" in action, (
            "write_trajectory_accepted must use captured.traj_path for per-run trajectory path"
        )

    def test_trajectory_path_in_rejected_state(self, loop_data: dict) -> None:
        action = loop_data["states"]["write_trajectory_rejected"].get("action", "")
        assert "captured.traj_path" in action, (
            "write_trajectory_rejected must use captured.traj_path for per-run trajectory path"
        )

    def test_description_references_new_path(self, loop_data: dict) -> None:
        description = loop_data.get("description", "")
        assert ".ll/runs/harness-optimize" in description, (
            "description must reference the new .ll/runs/harness-optimize trajectory path"
        )
        assert "harness-optimize-trajectory.jsonl" not in description, (
            "description must not reference the old hardcoded trajectory path"
        )

    def test_load_directive_no_old_path(self, loop_data: dict) -> None:
        action = loop_data["states"]["load_directive"].get("action", "")
        assert "harness-optimize-trajectory.jsonl" not in action, (
            "load_directive must not reference the old hardcoded trajectory path"
        )

    def test_init_run_state_is_shell_with_capture(self, loop_data: dict) -> None:
        state = loop_data["states"]["init_run"]
        assert state.get("action_type") == "shell"
        assert state.get("capture") == "traj_path"
        assert state.get("next") == "load_directive"

    def test_init_run_shell_creates_trajectory_directory(self, tmp_path: Path) -> None:
        import subprocess

        state_yaml_action = (
            'RUN_ID=$(date +%s%N)\n'
            'TRAJ=".ll/runs/harness-optimize/${RUN_ID}/states/whole-file/trajectory.jsonl"\n'
            'mkdir -p "$(dirname "$TRAJ")"\n'
            'echo "$TRAJ"\n'
        )
        result = subprocess.run(
            ["bash", "-c", state_yaml_action],
            capture_output=True,
            text=True,
            cwd=tmp_path,
        )
        assert result.returncode == 0, f"init_run action failed: {result.stderr}"
        traj_path = result.stdout.strip()
        assert ".ll/runs/harness-optimize" in traj_path
        assert traj_path.endswith("trajectory.jsonl")
        assert (tmp_path / traj_path).parent.is_dir(), f"Expected directory to exist: {(tmp_path / traj_path).parent}"


class TestYamlStateEditor:
    """Tests for yaml_state_editor.extract_action and replace_action."""

    FIXTURE_YAML = (
        "name: test-loop\n"
        "initial: first\n"
        "states:\n"
        "  first:\n"
        "    action: |\n"
        "      Do something first\n"
        "      Multi-line action text\n"
        "    prompt: first-prompt\n"
        "    on_yes: second\n"
        "    on_no: done\n"
        "  second:\n"
        "    action: |\n"
        "      Do something second\n"
        "      Another multi-line action\n"
        "    prompt: second-prompt\n"
        "    on_yes: done\n"
        "  done:\n"
        "    terminal: true\n"
    )

    @pytest.fixture
    def loop_yaml(self, tmp_path: Path) -> Path:
        path = tmp_path / "test-loop.yaml"
        path.write_text(self.FIXTURE_YAML)
        return path

    def test_extract_action_returns_correct_text_first(self, loop_yaml: Path) -> None:
        result = extract_action(loop_yaml, "first")
        assert "Do something first" in result
        assert "Multi-line action text" in result

    def test_extract_action_returns_correct_text_second(self, loop_yaml: Path) -> None:
        result = extract_action(loop_yaml, "second")
        assert "Do something second" in result
        assert "Another multi-line action" in result

    def test_extract_action_raises_for_unknown_state(self, loop_yaml: Path) -> None:
        with pytest.raises(KeyError):
            extract_action(loop_yaml, "nonexistent")

    def test_replace_action_modifies_only_target_state(self, loop_yaml: Path) -> None:
        replace_action(loop_yaml, "second", "New action text\nLine two\n")
        assert "New action text" in extract_action(loop_yaml, "second")
        # first state must be unchanged
        assert "Do something first" in extract_action(loop_yaml, "first")

    def test_replace_action_preserves_sibling_keys(self, loop_yaml: Path) -> None:
        replace_action(loop_yaml, "first", "Replacement text\n")
        import yaml

        data = yaml.safe_load(loop_yaml.read_text())
        assert data["states"]["first"]["prompt"] == "first-prompt"
        assert data["states"]["first"]["on_yes"] == "second"
        assert data["states"]["first"]["on_no"] == "done"

    def test_replace_action_leaves_other_states_unchanged(self, loop_yaml: Path) -> None:
        replace_action(loop_yaml, "first", "Changed\n")
        import yaml

        data = yaml.safe_load(loop_yaml.read_text())
        assert "Do something second" in data["states"]["second"]["action"]
        assert data["states"]["done"].get("terminal") is True

    def test_replace_action_preserves_block_scalar_style(self, loop_yaml: Path) -> None:
        replace_action(loop_yaml, "second", "Updated multi-line\naction content\n")
        raw = loop_yaml.read_text()
        # ruamel must emit `action: |` not `action: "..."` or `action: 'Updated...'`
        assert "action: |" in raw
