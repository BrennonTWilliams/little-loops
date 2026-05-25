"""Tests for the harness-optimize built-in loop."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import yaml

from little_loops.fsm.validation import ValidationSeverity, load_and_validate, validate_fsm
from little_loops.loops.yaml_state_editor import extract_action, replace_action


def _bash(script: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", "-c", script], cwd=cwd, capture_output=True, text=True)


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
        "dequeue_state",
        "check_queue",
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

    def test_write_trajectory_accepted_routes_based_on_mode(self, loop_data: dict) -> None:
        state = loop_data["states"]["write_trajectory_accepted"]
        assert state.get("next") is None, (
            "write_trajectory_accepted must use route dispatch, not static next"
        )
        assert state.get("on_yes") == "check_queue", (
            "write_trajectory_accepted must route to check_queue in state-mode (exit 0)"
        )
        assert state.get("on_no") == "capture_prev", (
            "write_trajectory_accepted must route to capture_prev in whole-file mode (exit 1)"
        )

    def test_write_trajectory_rejected_routes_based_on_mode(self, loop_data: dict) -> None:
        state = loop_data["states"]["write_trajectory_rejected"]
        assert state.get("next") is None, (
            "write_trajectory_rejected must use route dispatch, not static next"
        )
        assert state.get("on_yes") == "check_queue", (
            "write_trajectory_rejected must route to check_queue in state-mode (exit 0)"
        )
        assert state.get("on_no") == "done", (
            "write_trajectory_rejected must route to done in whole-file mode (exit 1)"
        )

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

    def test_init_run_shell_creates_trajectory_directory(
        self, loop_data: dict, tmp_path: Path
    ) -> None:
        import subprocess

        from little_loops.fsm.interpolation import InterpolationContext, interpolate

        raw_action = loop_data["states"]["init_run"]["action"]
        bash_script = interpolate(raw_action, InterpolationContext())
        result = subprocess.run(
            ["bash", "-c", bash_script],
            capture_output=True,
            text=True,
            cwd=tmp_path,
        )
        assert result.returncode == 0, f"init_run action failed: {result.stderr}"
        traj_path = result.stdout.strip()
        assert ".ll/runs/harness-optimize" in traj_path
        assert traj_path.endswith("trajectory.jsonl")
        assert (tmp_path / traj_path).parent.is_dir(), (
            f"Expected directory to exist: {(tmp_path / traj_path).parent}"
        )


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


# ---------------------------------------------------------------------------
# Bash snippets extracted from dequeue_state and check_queue states
# ---------------------------------------------------------------------------

_DEQUEUE_SCRIPT = r"""
ENTRY=$(head -1 .loops/tmp/harness-optimize-state-queue.txt)
tail -n +2 .loops/tmp/harness-optimize-state-queue.txt \
  > .loops/tmp/harness-optimize-state-queue.tmp
mv .loops/tmp/harness-optimize-state-queue.tmp \
  .loops/tmp/harness-optimize-state-queue.txt
STATE_NAME=$(echo "$ENTRY" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['name'])")
EXAMPLES_FILE=$(echo "$ENTRY" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('examples_file',''))")
printf '%s' "$STATE_NAME" > .loops/tmp/harness-optimize-state-name.txt
printf '%s' "$EXAMPLES_FILE" > .loops/tmp/harness-optimize-examples-file.txt
echo "$STATE_NAME"
"""

_CHECK_QUEUE_SCRIPT = r"""
if [ ! -s .loops/tmp/harness-optimize-state-queue.txt ]; then
  exit 1
fi
"""


class TestDequeueState:
    """dequeue_state queue pop and capture logic."""

    def test_pops_first_entry_and_emits_state_name(self, tmp_path: Path) -> None:
        loops_tmp = tmp_path / ".loops" / "tmp"
        loops_tmp.mkdir(parents=True)
        entry1 = json.dumps({"name": "state_a", "examples_file": "examples/a.txt"})
        entry2 = json.dumps({"name": "state_b", "examples_file": "examples/b.txt"})
        (loops_tmp / "harness-optimize-state-queue.txt").write_text(f"{entry1}\n{entry2}\n")

        result = _bash(_DEQUEUE_SCRIPT, tmp_path)

        assert result.returncode == 0, f"dequeue_state failed: {result.stderr}"
        assert result.stdout.strip() == "state_a"
        queue = (loops_tmp / "harness-optimize-state-queue.txt").read_text()
        assert "state_a" not in queue
        assert "state_b" in queue

    def test_writes_state_name_to_temp_file(self, tmp_path: Path) -> None:
        loops_tmp = tmp_path / ".loops" / "tmp"
        loops_tmp.mkdir(parents=True)
        entry = json.dumps({"name": "optimize_trigger", "examples_file": "ex.txt"})
        (loops_tmp / "harness-optimize-state-queue.txt").write_text(f"{entry}\n")

        _bash(_DEQUEUE_SCRIPT, tmp_path)

        assert (loops_tmp / "harness-optimize-state-name.txt").read_text() == "optimize_trigger"

    def test_writes_examples_file_to_temp_file(self, tmp_path: Path) -> None:
        loops_tmp = tmp_path / ".loops" / "tmp"
        loops_tmp.mkdir(parents=True)
        entry = json.dumps({"name": "some_state", "examples_file": "examples/test.txt"})
        (loops_tmp / "harness-optimize-state-queue.txt").write_text(f"{entry}\n")

        _bash(_DEQUEUE_SCRIPT, tmp_path)

        assert (loops_tmp / "harness-optimize-examples-file.txt").read_text() == "examples/test.txt"

    def test_advances_queue_after_each_pop(self, tmp_path: Path) -> None:
        loops_tmp = tmp_path / ".loops" / "tmp"
        loops_tmp.mkdir(parents=True)
        entries = (
            "\n".join(json.dumps({"name": f"state_{i}", "examples_file": ""}) for i in range(3))
            + "\n"
        )
        (loops_tmp / "harness-optimize-state-queue.txt").write_text(entries)

        _bash(_DEQUEUE_SCRIPT, tmp_path)
        _bash(_DEQUEUE_SCRIPT, tmp_path)
        result = _bash(_DEQUEUE_SCRIPT, tmp_path)

        assert result.stdout.strip() == "state_2"
        assert (loops_tmp / "harness-optimize-state-queue.txt").read_text().strip() == ""

    def test_empty_examples_file_field_writes_empty_string(self, tmp_path: Path) -> None:
        loops_tmp = tmp_path / ".loops" / "tmp"
        loops_tmp.mkdir(parents=True)
        entry = json.dumps({"name": "bare_state"})
        (loops_tmp / "harness-optimize-state-queue.txt").write_text(f"{entry}\n")

        _bash(_DEQUEUE_SCRIPT, tmp_path)

        assert (loops_tmp / "harness-optimize-examples-file.txt").read_text() == ""


class TestCheckQueue:
    """check_queue routing logic."""

    def test_exits_1_when_queue_file_empty(self, tmp_path: Path) -> None:
        loops_tmp = tmp_path / ".loops" / "tmp"
        loops_tmp.mkdir(parents=True)
        (loops_tmp / "harness-optimize-state-queue.txt").write_text("")

        result = _bash(_CHECK_QUEUE_SCRIPT, tmp_path)

        assert result.returncode != 0

    def test_exits_1_when_queue_file_missing(self, tmp_path: Path) -> None:
        loops_tmp = tmp_path / ".loops" / "tmp"
        loops_tmp.mkdir(parents=True)

        result = _bash(_CHECK_QUEUE_SCRIPT, tmp_path)

        assert result.returncode != 0

    def test_exits_0_when_queue_non_empty(self, tmp_path: Path) -> None:
        loops_tmp = tmp_path / ".loops" / "tmp"
        loops_tmp.mkdir(parents=True)
        entry = json.dumps({"name": "state_a", "examples_file": ""})
        (loops_tmp / "harness-optimize-state-queue.txt").write_text(f"{entry}\n")

        result = _bash(_CHECK_QUEUE_SCRIPT, tmp_path)

        assert result.returncode == 0

    def test_exits_1_after_queue_drained(self, tmp_path: Path) -> None:
        loops_tmp = tmp_path / ".loops" / "tmp"
        loops_tmp.mkdir(parents=True)
        entry = json.dumps({"name": "only_state", "examples_file": ""})
        (loops_tmp / "harness-optimize-state-queue.txt").write_text(f"{entry}\n")

        _bash(_DEQUEUE_SCRIPT, tmp_path)
        result = _bash(_CHECK_QUEUE_SCRIPT, tmp_path)

        assert result.returncode != 0


class TestStateModeIntegration:
    """Integration tests for state-mode isolation using yaml_state_editor."""

    FIXTURE_LOOP_YAML = (
        "name: test-target-loop\n"
        "initial: first\n"
        "targets:\n"
        "  - file: test-target-loop.yaml\n"
        "    states:\n"
        "      - name: first\n"
        "        examples_file: examples/first.txt\n"
        "        eval: score\n"
        "      - name: second\n"
        "        examples_file: examples/second.txt\n"
        "        eval: score\n"
        "states:\n"
        "  first:\n"
        "    action: |\n"
        "      Do first action\n"
        "    next: second\n"
        "  second:\n"
        "    action: |\n"
        "      Do second action\n"
        "    next: done\n"
        "  done:\n"
        "    terminal: true\n"
    )

    @pytest.fixture
    def target_loop(self, tmp_path: Path) -> Path:
        path = tmp_path / "test-target-loop.yaml"
        path.write_text(self.FIXTURE_LOOP_YAML)
        return path

    def test_replace_first_state_leaves_second_unchanged(self, target_loop: Path) -> None:
        replace_action(target_loop, "first", "Optimized first action\n")

        assert "Optimized first action" in extract_action(target_loop, "first")
        assert "Do second action" in extract_action(target_loop, "second")

    def test_replace_second_state_leaves_first_unchanged(self, target_loop: Path) -> None:
        replace_action(target_loop, "second", "Optimized second action\n")

        assert "Do first action" in extract_action(target_loop, "first")
        assert "Optimized second action" in extract_action(target_loop, "second")

    def test_independent_mutations_preserve_yaml_structure(self, target_loop: Path) -> None:
        replace_action(target_loop, "first", "New first\n")
        replace_action(target_loop, "second", "New second\n")

        data = yaml.safe_load(target_loop.read_text())
        assert data["states"]["first"]["next"] == "second"
        assert data["states"]["second"]["next"] == "done"
        assert data["states"]["done"].get("terminal") is True

    def test_queue_written_from_loop_yaml_targets(self, tmp_path: Path, target_loop: Path) -> None:
        """load_directive queue-writing script populates state queue from targets[].states[]."""
        loops_tmp = tmp_path / ".loops" / "tmp"
        loops_tmp.mkdir(parents=True)

        write_queue_script = rf"""
LOOP_YAML="{target_loop}"
mkdir -p .loops/tmp
if [ -f "$LOOP_YAML" ]; then
  python3 - "$LOOP_YAML" 2>/dev/null <<'PYEOF'
import yaml, json, sys
data = yaml.safe_load(open(sys.argv[1]))
states = [s for t in data.get('targets', []) for s in t.get('states', [])]
if states:
    with open('.loops/tmp/harness-optimize-state-queue.txt', 'w') as f:
        for s in states:
            f.write(json.dumps({{'name': s['name'], 'examples_file': s.get('examples_file', '')}}) + '\n')
PYEOF
fi
"""
        result = _bash(write_queue_script, tmp_path)
        assert result.returncode == 0, f"queue write failed: {result.stderr}"

        queue_file = loops_tmp / "harness-optimize-state-queue.txt"
        assert queue_file.exists(), "queue file was not created"
        lines = [json.loads(ln) for ln in queue_file.read_text().strip().splitlines()]
        assert len(lines) == 2
        assert lines[0]["name"] == "first"
        assert lines[0]["examples_file"] == "examples/first.txt"
        assert lines[1]["name"] == "second"

    def test_no_queue_written_for_non_loop_yaml(self, tmp_path: Path) -> None:
        """load_directive does not write queue when target is a plain text file."""
        loops_tmp = tmp_path / ".loops" / "tmp"
        loops_tmp.mkdir(parents=True)
        plain_file = tmp_path / "SKILL.md"
        plain_file.write_text("# Skill\nSome content\n")

        write_queue_script = rf"""
LOOP_YAML="{plain_file}"
mkdir -p .loops/tmp
if [ -f "$LOOP_YAML" ]; then
  python3 - "$LOOP_YAML" 2>/dev/null <<'PYEOF'
import yaml, json, sys
data = yaml.safe_load(open(sys.argv[1]))
states = [s for t in data.get('targets', []) for s in t.get('states', [])]
if states:
    with open('.loops/tmp/harness-optimize-state-queue.txt', 'w') as f:
        for s in states:
            f.write(json.dumps({{'name': s['name'], 'examples_file': s.get('examples_file', '')}}) + '\n')
PYEOF
fi
"""
        _bash(write_queue_script, tmp_path)

        queue_file = loops_tmp / "harness-optimize-state-queue.txt"
        assert not queue_file.exists() or queue_file.read_text().strip() == ""
