"""Tests for the rn-plan-apo built-in loop (FEAT-1536)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from little_loops.fsm.fragments import resolve_fragments, resolve_inheritance
from little_loops.fsm.validation import ValidationSeverity, load_and_validate, validate_fsm

BUILTIN_LOOPS_DIR = Path(__file__).parent.parent / "little_loops" / "loops"
LOOP_FILE = BUILTIN_LOOPS_DIR / "rn-plan-apo.yaml"
SCORE_FRAGMENT_FILE = BUILTIN_LOOPS_DIR / "lib" / "score-plan-quality.yaml"


@pytest.fixture
def raw_data() -> dict:
    """Load the rn-plan-apo YAML before inheritance/fragment resolution."""
    assert LOOP_FILE.exists(), f"rn-plan-apo.yaml not found at {LOOP_FILE}"
    with open(LOOP_FILE) as f:
        return yaml.safe_load(f)


@pytest.fixture
def resolved_data() -> dict:
    """Load rn-plan-apo with inheritance and fragments fully resolved."""
    with open(LOOP_FILE) as f:
        raw = yaml.safe_load(f)
    raw = resolve_inheritance(raw, BUILTIN_LOOPS_DIR)
    raw = resolve_fragments(raw, BUILTIN_LOOPS_DIR)
    return raw


class TestRnPlanApoFile:
    """Structural tests for rn-plan-apo.yaml."""

    def test_file_exists(self) -> None:
        assert LOOP_FILE.exists(), f"rn-plan-apo.yaml not found at {LOOP_FILE}"

    def test_parses_as_yaml(self, raw_data: dict) -> None:
        assert isinstance(raw_data, dict)

    def test_validates_as_fsm(self) -> None:
        fsm, _ = load_and_validate(LOOP_FILE)
        errors = validate_fsm(fsm)
        error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        assert not error_list, f"FSM validation errors: {[str(e) for e in error_list]}"

    def test_name(self, raw_data: dict) -> None:
        assert raw_data.get("name") == "rn-plan-apo"

    def test_inherits_from_apo_base(self, raw_data: dict) -> None:
        """rn-plan-apo must declare `from: lib/apo-base` to inherit the APO scaffolding."""
        assert raw_data.get("from") == "lib/apo-base"

    def test_imports_score_plan_quality_fragment(self, raw_data: dict) -> None:
        """rn-plan-apo must import lib/score-plan-quality.yaml so score_plans can use the fragment."""
        imports = raw_data.get("import") or []
        assert "lib/score-plan-quality.yaml" in imports

    def test_initial_state(self, raw_data: dict) -> None:
        assert raw_data.get("initial") == "run_planner"

    def test_inherits_apo_category_max_iterations_timeout(self, resolved_data: dict) -> None:
        """category, max_iterations, and timeout must come from lib/apo-base."""
        assert resolved_data.get("category") == "apo"
        assert resolved_data.get("max_iterations") == 20
        assert resolved_data.get("timeout") == 3600

    def test_context_defaults(self, raw_data: dict) -> None:
        ctx = raw_data.get("context") or {}
        assert ctx.get("plan_prompt_file") == ".ll/prompts/rn-plan-planning.md"
        assert ctx.get("tasks_file") == "benchmarks/rn-plan-tasks.json"
        assert ctx.get("target_plan_quality") == 80

    def test_context_inherits_prompt_file_from_apo_base(self, resolved_data: dict) -> None:
        """prompt_file from lib/apo-base must survive deep-merge with the child context."""
        ctx = resolved_data.get("context") or {}
        assert ctx.get("prompt_file") == "system.md"

    def test_terminal_done_inherited(self, resolved_data: dict) -> None:
        """done state must be terminal (inherited from lib/apo-base)."""
        done = resolved_data["states"].get("done") or {}
        assert done.get("terminal") is True

    def test_required_states_exist(self, raw_data: dict) -> None:
        required = {
            "run_planner",
            "score_plans",
            "compute_gradient",
            "route_convergence",
            "apply_gradient",
        }
        actual = set(raw_data["states"].keys())
        missing = required - actual
        assert not missing, f"Missing states: {missing}"


class TestRunPlannerState:
    """run_planner executes rn-plan per task and captures the run directory."""

    def test_action_type_shell(self, raw_data: dict) -> None:
        state = raw_data["states"]["run_planner"]
        assert state.get("action_type") == "shell"

    def test_captures_plans(self, raw_data: dict) -> None:
        state = raw_data["states"]["run_planner"]
        assert state.get("capture") == "plans"

    def test_routes_to_score_plans(self, raw_data: dict) -> None:
        state = raw_data["states"]["run_planner"]
        assert state.get("next") == "score_plans"

    def test_invokes_rn_plan(self, raw_data: dict) -> None:
        """run_planner action must invoke `ll-loop run rn-plan` to delegate to the planner."""
        action = raw_data["states"]["run_planner"].get("action", "")
        assert "ll-loop run rn-plan" in action

    def test_references_tasks_file(self, raw_data: dict) -> None:
        action = raw_data["states"]["run_planner"].get("action", "")
        assert "${context.tasks_file}" in action

    def test_on_blocked_done(self, raw_data: dict) -> None:
        state = raw_data["states"]["run_planner"]
        assert state.get("on_blocked") == "done"


class TestScorePlansState:
    """score_plans uses the score_plan_quality fragment."""

    def test_declares_fragment(self, raw_data: dict) -> None:
        """In the raw YAML, score_plans must reference fragment: score_plan_quality."""
        state = raw_data["states"]["score_plans"]
        assert state.get("fragment") == "score_plan_quality"

    def test_resolves_to_prompt_with_timeout(self, resolved_data: dict) -> None:
        """After fragment resolution, score_plans must be a prompt state with the fragment's timeout."""
        state = resolved_data["states"]["score_plans"]
        assert state.get("action_type") == "prompt"
        assert state.get("timeout") == 300
        assert "fragment" not in state

    def test_captures_plan_scores(self, raw_data: dict) -> None:
        state = raw_data["states"]["score_plans"]
        assert state.get("capture") == "plan_scores"

    def test_routes_to_compute_gradient(self, raw_data: dict) -> None:
        state = raw_data["states"]["score_plans"]
        assert state.get("next") == "compute_gradient"

    def test_scores_four_dimensions(self, raw_data: dict) -> None:
        """Per AC: scoring must cover at least 4 dimensions."""
        action = raw_data["states"]["score_plans"].get("action", "")
        for dim in (
            "subtask_success_rate",
            "depth_complexity_ratio",
            "redundancy",
            "coverage_gaps",
        ):
            assert dim in action, f"score_plans action must reference dimension {dim!r}"

    def test_emits_plan_quality_aggregate(self, raw_data: dict) -> None:
        """score_plans must instruct the LLM to emit PLAN_QUALITY=<int> on the final line."""
        action = raw_data["states"]["score_plans"].get("action", "")
        assert "PLAN_QUALITY=" in action

    def test_on_blocked_done(self, raw_data: dict) -> None:
        state = raw_data["states"]["score_plans"]
        assert state.get("on_blocked") == "done"


class TestComputeGradientState:
    """compute_gradient produces a text gradient or emits CONVERGED."""

    def test_action_type_prompt(self, raw_data: dict) -> None:
        state = raw_data["states"]["compute_gradient"]
        assert state.get("action_type") == "prompt"

    def test_captures_gradient(self, raw_data: dict) -> None:
        state = raw_data["states"]["compute_gradient"]
        assert state.get("capture") == "gradient"

    def test_routes_to_route_convergence(self, raw_data: dict) -> None:
        state = raw_data["states"]["compute_gradient"]
        assert state.get("next") == "route_convergence"

    def test_action_consumes_plan_scores(self, raw_data: dict) -> None:
        action = raw_data["states"]["compute_gradient"].get("action", "")
        assert "${captured.plan_scores.output}" in action

    def test_action_emits_three_gradient_labels(self, raw_data: dict) -> None:
        action = raw_data["states"]["compute_gradient"].get("action", "")
        for label in ("FAILURE_PATTERN", "ROOT_CAUSE", "GRADIENT"):
            assert label in action

    def test_action_references_converged_sentinel(self, raw_data: dict) -> None:
        """compute_gradient must instruct the LLM to emit CONVERGED when target is exceeded."""
        action = raw_data["states"]["compute_gradient"].get("action", "")
        assert "CONVERGED" in action
        assert "${context.target_plan_quality}" in action

    def test_on_blocked_done(self, raw_data: dict) -> None:
        state = raw_data["states"]["compute_gradient"]
        assert state.get("on_blocked") == "done"


class TestRouteConvergenceState:
    """route_convergence is a pure evaluator over the prior gradient capture."""

    def test_has_no_action(self, raw_data: dict) -> None:
        state = raw_data["states"]["route_convergence"]
        assert "action" not in state
        assert "action_type" not in state

    def test_has_output_contains_evaluator(self, raw_data: dict) -> None:
        evaluator = raw_data["states"]["route_convergence"].get("evaluate", {})
        assert evaluator.get("type") == "output_contains"
        assert evaluator.get("pattern") == "CONVERGED"

    def test_route_convergence_evaluator_source(self, raw_data: dict) -> None:
        """Mirrors TestSvgTextgradLoop::test_route_convergence_evaluator_source.

        Without `source:`, the evaluator reads this state's empty output instead
        of the prior compute_gradient capture, so CONVERGED would never match.
        """
        evaluator = raw_data["states"]["route_convergence"].get("evaluate", {})
        assert evaluator.get("source") == "${captured.gradient.output}", (
            "route_convergence.evaluate must have "
            "'source: \"${captured.gradient.output}\"' so the evaluator reads "
            "the prior compute_gradient output, not this state's (empty) output"
        )

    def test_on_yes_routes_to_done(self, raw_data: dict) -> None:
        state = raw_data["states"]["route_convergence"]
        assert state.get("on_yes") == "done"

    def test_on_no_routes_to_apply_gradient(self, raw_data: dict) -> None:
        state = raw_data["states"]["route_convergence"]
        assert state.get("on_no") == "apply_gradient"

    def test_on_error_defined(self, raw_data: dict) -> None:
        """route_convergence must define on_error for graceful evaluator-failure fallback."""
        state = raw_data["states"]["route_convergence"]
        assert "on_error" in state


class TestApplyGradientState:
    """apply_gradient overwrites plan_prompt_file with a refined prompt."""

    def test_action_type_prompt(self, raw_data: dict) -> None:
        state = raw_data["states"]["apply_gradient"]
        assert state.get("action_type") == "prompt"

    def test_no_capture(self, raw_data: dict) -> None:
        """apply_gradient writes its artifact (the prompt file) to disk, not via capture."""
        state = raw_data["states"]["apply_gradient"]
        assert "capture" not in state

    def test_routes_back_to_run_planner(self, raw_data: dict) -> None:
        """apply_gradient closes the cycle by routing back to run_planner."""
        state = raw_data["states"]["apply_gradient"]
        assert state.get("next") == "run_planner"

    def test_action_references_plan_prompt_file(self, raw_data: dict) -> None:
        action = raw_data["states"]["apply_gradient"].get("action", "")
        assert "${context.plan_prompt_file}" in action

    def test_action_references_gradient_capture(self, raw_data: dict) -> None:
        action = raw_data["states"]["apply_gradient"].get("action", "")
        assert "${captured.gradient.output}" in action

    def test_action_overwrites_prompt_file(self, raw_data: dict) -> None:
        """apply_gradient must instruct the agent to overwrite plan_prompt_file."""
        action = raw_data["states"]["apply_gradient"].get("action", "")
        assert "overwrite" in action.lower()

    def test_on_blocked_done(self, raw_data: dict) -> None:
        state = raw_data["states"]["apply_gradient"]
        assert state.get("on_blocked") == "done"


class TestPromptFilePersistenceContract:
    """Structural invariants enforcing 'overwrite only on accepted refinements'."""

    def test_apply_gradient_unreachable_from_converged_branch(self, raw_data: dict) -> None:
        """When route_convergence.on_yes fires (CONVERGED), apply_gradient is unreachable.

        This is the structural guarantee for AC: 'loop overwrites
        plan_prompt_file only on accepted refinements; rejected refinements
        leave the file untouched.' The only path that touches the file is
        route_convergence -> on_no -> apply_gradient.
        """
        route = raw_data["states"]["route_convergence"]
        assert route.get("on_yes") == "done"
        assert route.get("on_no") == "apply_gradient"


class TestScorePlanQualityFragmentFile:
    """The lib/score-plan-quality.yaml fragment file exists and is structurally valid."""

    def test_file_exists(self) -> None:
        assert SCORE_FRAGMENT_FILE.exists(), (
            f"lib/score-plan-quality.yaml not found at {SCORE_FRAGMENT_FILE}"
        )

    def test_defines_score_plan_quality_fragment(self) -> None:
        with open(SCORE_FRAGMENT_FILE) as f:
            data = yaml.safe_load(f)
        fragments = data.get("fragments") or {}
        assert "score_plan_quality" in fragments
