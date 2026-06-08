"""Tests for the goal-cluster built-in orchestration loop (FEAT-1988)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from little_loops.fsm import is_runnable_loop
from little_loops.fsm.validation import (
    ValidationSeverity,
    load_and_validate,
)

BUILTIN_LOOPS_DIR = Path(__file__).parent.parent / "little_loops" / "loops"
LOOP_FILE = BUILTIN_LOOPS_DIR / "goal-cluster.yaml"
LIB_FILE = BUILTIN_LOOPS_DIR / "lib" / "composer.yaml"
ROUTER_FILE = BUILTIN_LOOPS_DIR / "loop-router.yaml"

REQUIRED_STATES = {
    "load_goals",
    "dedup_and_batch",
    "present_plan",
    "execute_cluster",
    "propagate_context",
    "synthesize_cluster_result",
    "present_result",
}


@pytest.fixture
def loop_data() -> dict:
    assert LOOP_FILE.exists(), f"goal-cluster.yaml not found at {LOOP_FILE}"
    with open(LOOP_FILE) as f:
        return yaml.safe_load(f)


@pytest.fixture
def lib_data() -> dict:
    assert LIB_FILE.exists(), f"lib/composer.yaml not found at {LIB_FILE}"
    with open(LIB_FILE) as f:
        return yaml.safe_load(f)


class TestGoalClusterFile:
    """Basic file and YAML-parse tests."""

    def test_file_exists(self) -> None:
        assert LOOP_FILE.exists(), f"goal-cluster.yaml not found at {LOOP_FILE}"

    def test_yaml_parses(self, loop_data: dict) -> None:
        assert isinstance(loop_data, dict)

    def test_has_name(self, loop_data: dict) -> None:
        assert loop_data.get("name") == "goal-cluster"

    def test_has_description(self, loop_data: dict) -> None:
        assert loop_data.get("description"), "goal-cluster.yaml must have a top-level description"

    def test_has_required_states(self, loop_data: dict) -> None:
        states = set(loop_data.get("states", {}).keys())
        missing = REQUIRED_STATES - states
        assert not missing, f"goal-cluster.yaml missing required states: {missing}"

    def test_is_runnable(self) -> None:
        assert is_runnable_loop(LOOP_FILE), f"{LOOP_FILE.name} is not recognized as runnable"

    def test_imports_composer_lib(self, loop_data: dict) -> None:
        imports = loop_data.get("import", [])
        assert "lib/composer.yaml" in imports, (
            "goal-cluster must import lib/composer.yaml for the reassess fragment"
        )

    def test_imports_common_lib(self, loop_data: dict) -> None:
        imports = loop_data.get("import", [])
        assert "lib/common.yaml" in imports, (
            "goal-cluster must import lib/common.yaml for queue_track / queue_pop fragments"
        )

    def test_category_is_orchestration(self, loop_data: dict) -> None:
        assert loop_data.get("category") == "orchestration"

    def test_initial_state_is_load_goals(self, loop_data: dict) -> None:
        assert loop_data.get("initial") == "load_goals"

    def test_artifacts_in_run_dir(self, loop_data: dict) -> None:
        """All intermediate artifact writes use ${context.run_dir} (MR-3 compliance)."""
        states = loop_data.get("states", {})
        violations = []
        for state_name, state in states.items():
            action = state.get("action", "")
            if ".loops/tmp" in action and "${context.run_dir}" not in action:
                violations.append(state_name)
        assert not violations, (
            f"States writing to bare .loops/tmp/ instead of ${{context.run_dir}}: {violations}"
        )


class TestGoalClusterFSMValidation:
    """FSM structural validation tests."""

    def test_fsm_validate_passes(self) -> None:
        fsm, warnings = load_and_validate(LOOP_FILE)
        errors = [w for w in warnings if w.severity == ValidationSeverity.ERROR]
        assert not errors, f"goal-cluster.yaml has validation errors: {[str(e) for e in errors]}"

    def test_no_mr1_violations(self) -> None:
        fsm, warnings = load_and_validate(LOOP_FILE)
        mr1_errors = [
            w for w in warnings if w.severity == ValidationSeverity.ERROR and "MR-1" in w.message
        ]
        assert not mr1_errors, (
            f"goal-cluster.yaml has MR-1 violations: {[str(e) for e in mr1_errors]}"
        )

    def test_no_mr3_violations(self) -> None:
        fsm, warnings = load_and_validate(LOOP_FILE)
        mr3_warnings = [
            w
            for w in warnings
            if w.severity in (ValidationSeverity.WARNING, ValidationSeverity.ERROR)
            and "MR-3" in w.message
        ]
        assert not mr3_warnings, (
            f"goal-cluster.yaml has MR-3 violations: {[str(w) for w in mr3_warnings]}"
        )


class TestGoalClusterInputNormalization:
    """Unit tests for the load_goals input-shape normalization logic."""

    def test_load_goals_state_exists(self, loop_data: dict) -> None:
        assert "load_goals" in loop_data.get("states", {})

    def test_load_goals_is_shell_action(self, loop_data: dict) -> None:
        state = loop_data["states"]["load_goals"]
        assert state.get("action_type") == "shell"

    def test_load_goals_handles_json_list_shape(self, loop_data: dict) -> None:
        action = loop_data["states"]["load_goals"].get("action", "")
        assert (
            "startswith('['" in action
            or "startswith('[')" in action
            or "startswith('[')" in action
            or "stripped.startswith('['" in action
        ), "load_goals must handle JSON list input shape"

    def test_load_goals_handles_epic_shape(self, loop_data: dict) -> None:
        action = loop_data["states"]["load_goals"].get("action", "")
        assert "EPIC-" in action, "load_goals must handle EPIC-NNN input shape"

    def test_load_goals_handles_multiline_fallback(self, loop_data: dict) -> None:
        action = loop_data["states"]["load_goals"].get("action", "")
        assert "splitlines" in action, (
            "load_goals must fall back to raw multi-line parsing (one goal per line)"
        )

    def test_load_goals_writes_goals_json(self, loop_data: dict) -> None:
        action = loop_data["states"]["load_goals"].get("action", "")
        assert "goals.json" in action, (
            "load_goals must write normalized list to ${context.run_dir}/goals.json"
        )

    def test_load_goals_exits_on_empty(self, loop_data: dict) -> None:
        action = loop_data["states"]["load_goals"].get("action", "")
        assert "sys.exit(1)" in action, "load_goals must exit 1 when no goals can be parsed"

    def test_load_goals_evaluates_exit_code(self, loop_data: dict) -> None:
        state = loop_data["states"]["load_goals"]
        evaluate = state.get("evaluate", {})
        assert evaluate.get("type") == "exit_code", (
            "load_goals must use exit_code evaluator (MR-1 non-LLM gate)"
        )

    def test_load_goals_epic_enumeration_uses_valid_json_flag(self, loop_data: dict) -> None:
        # BUG-015: '--format json' is not a valid `ll-issues list` flag; the valid flag
        # is '--json'. Using the wrong flag silently fails and falls through to the raw
        # fallback, yielding the EPIC id as a literal goal instead of its children.
        action = loop_data["states"]["load_goals"].get("action", "")
        assert "--format" not in action, (
            "load_goals must not use '--format json' (invalid ll-issues list flag); use '--json'"
        )
        assert "'--parent', epic_id, '--json'" in action, (
            "load_goals must enumerate EPIC children via 'll-issues list --parent <id> --json'"
        )

    def test_load_goals_fails_loudly_on_empty_epic(self, loop_data: dict) -> None:
        # BUG-015 AC#3: a named EPIC with zero children must fail loudly, not fall
        # through to the raw-text fallback (which re-adds the EPIC id as a literal goal).
        action = loop_data["states"]["load_goals"].get("action", "")
        assert "epic_matched" in action and "has no child issues" in action, (
            "load_goals must exit 1 with a warning when a named EPIC enumerates zero children"
        )


class TestGoalClusterDedupBatch:
    """Tests for the dedup_and_batch state structure."""

    def test_dedup_and_batch_is_prompt(self, loop_data: dict) -> None:
        state = loop_data["states"]["dedup_and_batch"]
        assert state.get("action_type") == "prompt"

    def test_dedup_and_batch_captures_raw(self, loop_data: dict) -> None:
        state = loop_data["states"]["dedup_and_batch"]
        assert state.get("capture") == "batch_plan_raw"

    def test_dedup_and_batch_emits_batch_plan_tag(self, loop_data: dict) -> None:
        action = loop_data["states"]["dedup_and_batch"].get("action", "")
        assert "BATCH_PLAN:" in action, (
            "dedup_and_batch prompt must include BATCH_PLAN: emission format"
        )

    def test_dedup_and_batch_forbids_goal_cluster_as_loop(self, loop_data: dict) -> None:
        action = loop_data["states"]["dedup_and_batch"].get("action", "")
        assert "goal-cluster" in action, (
            "dedup_and_batch must instruct the LLM to never suggest goal-cluster as a sub-loop"
        )

    def test_dedup_and_batch_uses_llm_structured_evaluator(self, loop_data: dict) -> None:
        state = loop_data["states"]["dedup_and_batch"]
        evaluate = state.get("evaluate", {})
        assert evaluate.get("type") == "llm_structured", (
            "dedup_and_batch must use llm_structured evaluator per issue spec"
        )

    def test_dedup_and_batch_has_full_routing(self, loop_data: dict) -> None:
        state = loop_data["states"]["dedup_and_batch"]
        assert "on_yes" in state
        assert "on_no" in state
        assert "on_partial" in state


class TestGoalClusterReassessIntegration:
    """Tests for the reassess fragment usage in goal-cluster."""

    def test_reassess_fragment_referenced(self, loop_data: dict) -> None:
        states = loop_data.get("states", {})
        reassess_states = [name for name, s in states.items() if s.get("fragment") == "reassess"]
        assert reassess_states, (
            "goal-cluster must reference the 'reassess' fragment from lib/composer.yaml"
        )

    def test_reassess_state_has_full_routing(self, loop_data: dict) -> None:
        states = loop_data.get("states", {})
        for name, s in states.items():
            if s.get("fragment") == "reassess":
                assert "on_yes" in s, f"reassess state '{name}' missing on_yes"
                assert "on_no" in s, f"reassess state '{name}' missing on_no"
                assert "on_partial" in s, f"reassess state '{name}' missing on_partial"


class TestGoalClusterDispatch:
    """Tests for the dispatch_cluster sub-loop hand-off contract."""

    def test_dispatch_cluster_passes_goal_key_not_input(self, loop_data: dict) -> None:
        # BUG-016: sub-loops (loop-router et al.) declare their primary input as
        # `goal` (input_key: goal). Passing `with: {input: ...}` leaves context.goal
        # empty, so classify_goal sees an empty GOAL and routes to propose_new_loop.
        with_block = loop_data["states"]["dispatch_cluster"].get("with", {})
        assert "goal" in with_block, (
            "dispatch_cluster must pass the batch goal under the 'goal' key "
            "(sub-loops declare input_key: goal)"
        )
        assert "input" not in with_block, (
            "dispatch_cluster must not pass the batch goal under 'input' — "
            "loop-router ignores context.input and reads context.goal"
        )


class TestCatalogExclusivity:
    """Tests for the routing guard — loop-router and lib/composer must exclude goal-cluster."""

    @pytest.fixture
    def router_data(self) -> dict:
        assert ROUTER_FILE.exists(), f"loop-router.yaml not found at {ROUTER_FILE}"
        with open(ROUTER_FILE) as f:
            return yaml.safe_load(f)

    def test_loop_router_excludes_goal_cluster(self, router_data: dict) -> None:
        """loop-router must exclude goal-cluster from its catalog discovery.

        Routing guard: loop-router should not present goal-cluster as a candidate
        for a single-goal input. goal-cluster is for multi-goal inputs only.
        """
        action = router_data.get("states", {}).get("discover_loops", {}).get("action", "")
        assert "goal-cluster" in action, (
            "loop-router's discover_loops must add goal-cluster to excludes"
        )

    def test_discover_loops_fragment_excludes_goal_cluster(self, lib_data: dict) -> None:
        """lib/composer.yaml discover_loops fragment must exclude goal-cluster.

        Prevents loop-composer from presenting goal-cluster as a candidate sub-loop
        (which would create a recursive orchestration cycle).
        """
        action = lib_data["fragments"]["discover_loops"].get("action", "")
        assert "goal-cluster" in action, (
            "lib/composer.yaml discover_loops fragment must exclude 'goal-cluster' from candidates"
        )


@pytest.mark.slow
class TestGoalClusterLiveValidation:
    """Optional live validation tests (skipped unless --run-slow flag is passed)."""

    def test_ll_loop_validate_passes(self) -> None:
        import subprocess

        result = subprocess.run(
            ["ll-loop", "validate", str(LOOP_FILE)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, (
            f"ll-loop validate failed for goal-cluster.yaml:\n{result.stdout}\n{result.stderr}"
        )
