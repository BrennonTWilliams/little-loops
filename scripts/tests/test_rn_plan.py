"""Tests for the rn-plan built-in FSM loop (FEAT-1534)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

from little_loops.fsm.validation import ValidationSeverity, load_and_validate, validate_fsm

BUILTIN_LOOPS_DIR = Path(__file__).parent.parent / "little_loops" / "loops"
LOOP_FILE = BUILTIN_LOOPS_DIR / "rn-plan.yaml"


def _bash(script: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", "-c", script], cwd=cwd, capture_output=True, text=True)


class TestRnPlanYaml:
    """Validate the rn-plan YAML parses and passes FSM validation."""

    @pytest.fixture
    def data(self) -> dict:
        assert LOOP_FILE.exists(), f"Loop file not found: {LOOP_FILE}"
        return yaml.safe_load(LOOP_FILE.read_text())

    def test_file_exists(self) -> None:
        assert LOOP_FILE.exists()

    def test_yaml_parses(self, data: dict) -> None:
        assert isinstance(data, dict)

    def test_fsm_validates_without_errors(self) -> None:
        fsm, _ = load_and_validate(LOOP_FILE)
        errors = validate_fsm(fsm)
        error_msgs = [r for r in errors if r.severity == ValidationSeverity.ERROR]
        assert not error_msgs, f"FSM validation errors: {error_msgs}"

    def test_description_is_present(self, data: dict) -> None:
        assert data.get("description"), "rn-plan must have a non-empty description"

    def test_required_top_level_fields(self, data: dict) -> None:
        assert data.get("name") == "rn-plan"
        assert data.get("initial") == "init"
        assert data.get("input_key") == "task"
        assert isinstance(data.get("states"), dict)

    def test_required_states_exist(self, data: dict) -> None:
        required = {
            "init",
            "generate_rubric",
            "classify_research",
            "route_files",
            "route_web",
            "research_files",
            "research_web",
            "synthesize",
            "score",
            "diagnose",
            "done",
            "failed",
        }
        actual = set(data["states"].keys())
        missing = required - actual
        assert not missing, f"Missing required states: {missing}"

    def test_init_state_is_shell_with_capture(self, data: dict) -> None:
        state = data["states"]["init"]
        assert state.get("action_type") == "shell"
        assert state.get("capture") == "run_dir"
        assert state.get("next") == "generate_rubric"

    def test_init_action_uses_absolute_path(self, data: dict) -> None:
        action = data["states"]["init"].get("action", "")
        assert "$(pwd)" in action, "init.action must use $(pwd) for an absolute path"

    def test_classify_research_captures_classification(self, data: dict) -> None:
        state = data["states"]["classify_research"]
        assert state.get("capture") == "classification"
        assert state.get("next") == "route_files"

    def test_route_files_is_output_contains_evaluator(self, data: dict) -> None:
        state = data["states"]["route_files"]
        evaluator = state.get("evaluate", {})
        assert evaluator.get("type") == "output_contains"
        assert evaluator.get("pattern") == "NEEDS_FILES"
        assert state.get("on_yes") == "research_files"
        assert state.get("on_no") == "route_web"

    def test_route_web_is_output_contains_evaluator(self, data: dict) -> None:
        state = data["states"]["route_web"]
        evaluator = state.get("evaluate", {})
        assert evaluator.get("type") == "output_contains"
        assert evaluator.get("pattern") == "NEEDS_WEB"
        assert state.get("on_yes") == "research_web"

    def test_score_state_uses_all_very_high_sentinel(self, data: dict) -> None:
        state = data["states"]["score"]
        evaluator = state.get("evaluate", {})
        assert evaluator.get("type") == "output_contains"
        assert evaluator.get("pattern") == "ALL_VERY_HIGH"
        assert state.get("on_yes") == "done"
        assert state.get("on_no") == "classify_research"
        assert state.get("on_error") == "diagnose"

    def test_done_state_is_terminal(self, data: dict) -> None:
        assert data["states"]["done"].get("terminal") is True

    def test_failed_state_is_terminal(self, data: dict) -> None:
        assert data["states"]["failed"].get("terminal") is True

    def test_context_has_task_and_output_dir(self, data: dict) -> None:
        ctx = data.get("context", {})
        assert "task" in ctx
        assert "output_dir" in ctx
        assert ctx["output_dir"] == ".loops/plans"

    def test_max_iterations_is_50(self, data: dict) -> None:
        assert data.get("max_iterations") == 50

    def test_router_states_have_on_error(self, data: dict) -> None:
        for state_name in ("route_files", "route_web"):
            state = data["states"][state_name]
            assert "on_error" in state, f"{state_name} must have on_error"

    def test_rubric_dimensions_mentioned_in_score_action(self, data: dict) -> None:
        action = data["states"]["score"].get("action", "")
        dimensions = [
            "breadth",
            "depth",
            "complexity",
            "clarity",
            "consistency",
            "logic_strategy",
        ]
        missing = [d for d in dimensions if d not in action]
        assert not missing, f"Score action missing rubric dimensions: {missing}"


class TestRnPlanShellStates:
    """Exercise the init shell action directly to verify slug and directory creation."""

    def test_init_creates_run_directory(self, tmp_path: Path) -> None:
        """init action creates the output directory under output_dir."""
        task = "Build a REST API for user authentication"
        # Use a relative output_dir so $(pwd)/$DIR produces a valid absolute path
        script = f"""
SLUG=$(echo "{task}" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '-' | sed 's/-\\+/-/g; s/^-//; s/-$//')
SLUG="${{SLUG:-rn-plan-run}}"
DIR=".loops/plans/$SLUG"
mkdir -p "$DIR"
: > "$DIR/plan.md"
: > "$DIR/plan-rubric.md"
: > "$DIR/research.md"
echo "$(pwd)/$DIR"
"""
        result = _bash(script, tmp_path)
        assert result.returncode == 0, f"init shell failed: {result.stderr}"
        run_dir = result.stdout.strip()
        assert run_dir, "init must output the run directory path"

        run_path = Path(run_dir)
        assert run_path.is_dir(), f"Run directory not created: {run_path}"
        assert (run_path / "plan.md").exists(), "plan.md not created"
        assert (run_path / "plan-rubric.md").exists(), "plan-rubric.md not created"
        assert (run_path / "research.md").exists(), "research.md not created"

    def test_init_slug_is_lowercase_hyphenated(self, tmp_path: Path) -> None:
        """init action produces a lowercase, hyphenated slug from the task."""
        output_dir = tmp_path / ".loops" / "plans"
        output_dir.mkdir(parents=True)

        task = "Migrate Hooks Adapter Layer"
        script = f"""
SLUG=$(echo "{task}" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '-' | sed 's/-\\+/-/g; s/^-//; s/-$//')
echo "$SLUG"
"""
        result = _bash(script, tmp_path)
        assert result.returncode == 0
        slug = result.stdout.strip()
        assert slug == "migrate-hooks-adapter-layer"

    def test_init_outputs_absolute_path(self, tmp_path: Path) -> None:
        """init action echoes an absolute path (starts with /)."""
        output_dir = tmp_path / ".loops" / "plans"
        output_dir.mkdir(parents=True)

        task = "simple task"
        script = f"""
SLUG=$(echo "{task}" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '-' | sed 's/-\\+/-/g; s/^-//; s/-$//')
DIR="{output_dir}/$SLUG"
mkdir -p "$DIR"
echo "$(pwd)/$DIR"
"""
        result = _bash(script, tmp_path)
        assert result.returncode == 0
        path = result.stdout.strip()
        assert path.startswith("/"), f"init must output absolute path, got: {path!r}"

    def test_init_empty_task_uses_fallback_slug(self, tmp_path: Path) -> None:
        """init action falls back to 'rn-plan-run' when task produces empty slug."""
        output_dir = tmp_path / ".loops" / "plans"
        output_dir.mkdir(parents=True)

        script = """
SLUG=$(echo "" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '-' | sed 's/-\\+/-/g; s/^-//; s/-$//')
SLUG="${SLUG:-rn-plan-run}"
echo "$SLUG"
"""
        result = _bash(script, tmp_path)
        assert result.returncode == 0
        slug = result.stdout.strip()
        assert slug == "rn-plan-run"


class TestRnPlanExecution:
    """End-to-end tests exercising rn-plan via the ll-loop CLI entry point."""

    def test_loop_resolves_as_builtin(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ll-loop can resolve rn-plan as a built-in loop without local YAML."""
        from little_loops.cli.loop._helpers import get_builtin_loops_dir, resolve_loop_path

        monkeypatch.chdir(tmp_path)
        result = resolve_loop_path("rn-plan", get_builtin_loops_dir())
        assert result is not None, "rn-plan should resolve as a built-in loop"
        assert result.name == "rn-plan.yaml"
        assert result.exists()

    def test_loop_loads_with_task_input(self) -> None:
        """FSMLoop loads from rn-plan.yaml and input_key routes task into context."""
        fsm, _ = load_and_validate(LOOP_FILE)
        assert fsm.input_key == "task"
        assert "task" in fsm.context
        assert fsm.initial == "init"

    def test_loop_dry_run_shows_loop_name(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """ll-loop run --dry-run for rn-plan outputs the loop name and task context."""
        import sys
        from unittest.mock import patch

        from little_loops.cli import main_loop

        monkeypatch.chdir(tmp_path)

        with patch.object(sys, "argv", ["ll-loop", "run", "rn-plan", "test task", "--dry-run"]):
            result = main_loop()

        captured = capsys.readouterr()
        assert "rn-plan" in captured.out
        # dry-run exits 0
        assert result == 0

    def test_score_state_output_contains_evaluator_matches_sentinel(self) -> None:
        """score state routing: ALL_VERY_HIGH → done, ITERATE → classify_research."""
        from little_loops.fsm.evaluators import evaluate_output_contains

        data = yaml.safe_load(LOOP_FILE.read_text())
        score_state = data["states"]["score"]
        pattern = score_state["evaluate"]["pattern"]

        assert evaluate_output_contains("ALL_VERY_HIGH\n", pattern).verdict == "yes"
        assert evaluate_output_contains("ITERATE\n", pattern).verdict == "no"
        assert (
            evaluate_output_contains("breadth: VERY-HIGH\nALL_VERY_HIGH", pattern).verdict == "yes"
        )
