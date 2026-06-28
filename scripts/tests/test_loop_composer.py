"""Tests for the loop-composer built-in orchestration loop (FEAT-1808)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from little_loops.fsm import is_runnable_loop
from little_loops.fsm.validation import (
    ValidationSeverity,
    load_and_validate,
    validate_fsm,
)

BUILTIN_LOOPS_DIR = Path(__file__).parent.parent / "little_loops" / "loops"
LOOP_FILE = BUILTIN_LOOPS_DIR / "loop-composer.yaml"
LIB_FILE = BUILTIN_LOOPS_DIR / "lib" / "composer.yaml"
ROUTER_FILE = BUILTIN_LOOPS_DIR / "loop-router.yaml"

REQUIRED_STATES = {
    "discover_loops",
    "decompose_goal",
    "parse_plan",
    "validate_plan",
    "re_decompose",
    "check_auto_plan",
    "present_plan",
    "execute_plan",
    "read_step_loop",
    "read_step_input",
    "dispatch_step",
    "write_step_success",
    "write_step_failed",
    "read_checkpoints",
    "review_chain",
    "present_result",
    "failed",
}


class TestLoopComposerFile:
    """Structural tests for loop-composer.yaml top-level fields."""

    @pytest.fixture
    def loop_data(self) -> dict:
        assert LOOP_FILE.exists(), f"loop-composer.yaml not found at {LOOP_FILE}"
        with open(LOOP_FILE) as f:
            return yaml.safe_load(f)

    def test_file_exists(self) -> None:
        assert LOOP_FILE.exists(), f"loop-composer.yaml not found at {LOOP_FILE}"

    def test_parses_as_yaml(self, loop_data: dict) -> None:
        assert isinstance(loop_data, dict)

    def test_validates_as_fsm(self) -> None:
        fsm, _ = load_and_validate(LOOP_FILE)
        errors = validate_fsm(fsm)
        error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        assert not error_list, f"loop-composer validation errors: {[str(e) for e in error_list]}"

    def test_name(self, loop_data: dict) -> None:
        assert loop_data.get("name") == "loop-composer"

    def test_category(self, loop_data: dict) -> None:
        assert loop_data.get("category") == "orchestration"

    def test_input_key(self, loop_data: dict) -> None:
        assert loop_data.get("input_key") == "goal"

    def test_initial_state(self, loop_data: dict) -> None:
        assert loop_data.get("initial") == "discover_loops"

    def test_description_exists(self, loop_data: dict) -> None:
        assert loop_data.get("description"), "loop-composer must have a top-level description"

    def test_context_variables(self, loop_data: dict) -> None:
        ctx = loop_data.get("context", {})
        for key in ("goal", "auto", "include", "exclude", "max_plan_nodes"):
            assert key in ctx, f"context missing key: {key}"

    def test_context_defaults(self, loop_data: dict) -> None:
        ctx = loop_data.get("context", {})
        assert ctx.get("auto") == "false", "auto must default to 'false' (HITL required)"
        assert ctx.get("max_plan_nodes") == "8"
        assert ctx.get("include") == ""
        assert ctx.get("exclude") == ""
        assert ctx.get("goal") == ""


class TestLoopComposerStates:
    """Per-state structural assertions for loop-composer.yaml."""

    @pytest.fixture
    def loop_data(self) -> dict:
        with open(LOOP_FILE) as f:
            return yaml.safe_load(f)

    @pytest.fixture
    def states(self, loop_data: dict) -> dict:
        return loop_data.get("states", {})

    def test_has_all_required_states(self, states: dict) -> None:
        actual = set(states.keys())
        missing = REQUIRED_STATES - actual
        extra = actual - REQUIRED_STATES
        assert not missing, f"loop-composer missing states: {missing}"
        assert not extra, f"loop-composer has unexpected states: {extra}"

    def test_discover_loops_imports_composer_lib(self, loop_data: dict) -> None:
        imports = loop_data.get("import", [])
        assert "lib/composer.yaml" in imports, (
            "loop-composer must import lib/composer.yaml for shared fragments"
        )

    def test_dispatch_step_uses_loop_field(self, states: dict) -> None:
        dispatch = states["dispatch_step"]
        assert "loop" in dispatch, "dispatch_step must use the loop: field for sub-loop dispatch"
        assert dispatch.get("capture") == "step_output"

    def test_dispatch_step_routes_success_and_failure(self, states: dict) -> None:
        dispatch = states["dispatch_step"]
        assert dispatch.get("on_yes") == "write_step_success"
        assert dispatch.get("on_no") == "write_step_failed"
        assert dispatch.get("on_error") == "write_step_failed"

    def test_present_plan_is_prompt_with_cancel(self, states: dict) -> None:
        # present_plan is a fragment — after resolve it has these fields set
        present = states["present_plan"]
        # The state references a fragment; raw YAML has fragment: present_plan
        # We check the fragment key or, if already resolved, the action_type
        has_fragment_ref = present.get("fragment") == "present_plan"
        # Either it references the fragment or it's already been resolved
        assert has_fragment_ref or present.get("action_type") == "prompt", (
            "present_plan must reference the present_plan fragment or be a prompt type"
        )
        # Routing: CANCEL → abort, APPROVE → execute
        assert present.get("on_yes") == "present_result", "CANCEL path must go to present_result"
        assert present.get("on_no") == "execute_plan", "APPROVE path must go to execute_plan"

    def test_present_result_is_terminal(self, states: dict) -> None:
        assert states["present_result"].get("terminal") is True

    def test_failed_is_terminal(self, states: dict) -> None:
        assert states["failed"].get("terminal") is True

    def test_execute_plan_routes_to_step_and_done(self, states: dict) -> None:
        ep = states["execute_plan"]
        assert ep.get("on_yes") == "read_step_loop", "step found → read_step_loop"
        assert ep.get("on_no") == "read_checkpoints", "all done → read_checkpoints"

    def test_write_step_success_goes_to_execute_plan(self, states: dict) -> None:
        ws = states["write_step_success"]
        assert ws.get("next") == "execute_plan", (
            "write_step_success must loop back to execute_plan for next step"
        )

    def test_write_step_failed_goes_to_read_checkpoints(self, states: dict) -> None:
        wf = states["write_step_failed"]
        assert wf.get("next") == "read_checkpoints", (
            "write_step_failed must proceed to read_checkpoints (MVP: stop on failure)"
        )

    def test_no_state_interpolates_captured_output_into_python_literal(self, states: dict) -> None:
        # Fix #5: shell states must read captured sub-loop/LLM output from disk
        # (via a quoted heredoc), never `"""${captured.X.output}"""`, which a
        # JSONL value containing quotes/backslashes/triple-quotes would corrupt.
        for name, state in states.items():
            action = state.get("action", "") or ""
            assert '"""${captured' not in action, (
                f"State {name!r} interpolates a captured value into a Python triple-quoted "
                f"literal — read it from disk via a quoted heredoc instead (fix #5)"
            )

    def test_no_loops_tmp_paths(self, states: dict) -> None:
        """MR-3 guard: no state action should write to .loops/tmp/."""
        for state_name, state in states.items():
            action = state.get("action", "") or ""
            assert ".loops/tmp" not in action, (
                f"State {state_name!r} writes to .loops/tmp/ — use ${{context.run_dir}}/ instead (MR-3)"
            )

    def test_uses_run_dir_for_artifacts(self, states: dict) -> None:
        """At least one state must reference ${context.run_dir} for per-run isolation."""
        any_run_dir = any(
            "${context.run_dir}" in (state.get("action", "") or "") for state in states.values()
        )
        assert any_run_dir, "No state references ${context.run_dir} — artifact isolation missing"


class TestComposerLibFragment:
    """Tests for the shared lib/composer.yaml fragment library."""

    @pytest.fixture
    def lib_data(self) -> dict:
        assert LIB_FILE.exists(), f"lib/composer.yaml not found at {LIB_FILE}"
        with open(LIB_FILE) as f:
            return yaml.safe_load(f)

    def test_lib_file_exists(self) -> None:
        assert LIB_FILE.exists(), f"lib/composer.yaml must exist at {LIB_FILE}"

    def test_lib_parses_as_yaml(self, lib_data: dict) -> None:
        assert isinstance(lib_data, dict)

    def test_lib_has_fragments_key(self, lib_data: dict) -> None:
        assert "fragments" in lib_data, (
            "lib/composer.yaml must have a top-level 'fragments:' mapping"
        )

    def test_lib_has_no_initial_key(self, lib_data: dict) -> None:
        """lib/composer.yaml must not have an initial: key — fragment libraries are not runnable."""
        assert "initial" not in lib_data, (
            "lib/composer.yaml must not define 'initial:' — it is a fragment library, not a runnable loop "
            "(required for test_doc_counts.py::test_lib_fragments_are_not_runnable)"
        )

    def test_lib_is_not_runnable(self) -> None:
        assert not is_runnable_loop(LIB_FILE), (
            "lib/composer.yaml must not be classified as a runnable loop"
        )

    def test_lib_has_discover_loops_fragment(self, lib_data: dict) -> None:
        assert "discover_loops" in lib_data["fragments"]

    def test_lib_has_validate_plan_fragment(self, lib_data: dict) -> None:
        assert "validate_plan" in lib_data["fragments"]

    def test_lib_has_present_plan_fragment(self, lib_data: dict) -> None:
        assert "present_plan" in lib_data["fragments"]

    def test_discover_loops_fragment_excludes_router(self, lib_data: dict) -> None:
        action = lib_data["fragments"]["discover_loops"].get("action", "")
        assert "loop-router" in action, (
            "discover_loops fragment must exclude 'loop-router' from the candidate catalog"
        )

    def test_discover_loops_fragment_excludes_composer(self, lib_data: dict) -> None:
        action = lib_data["fragments"]["discover_loops"].get("action", "")
        assert "loop-composer" in action, (
            "discover_loops fragment must exclude 'loop-composer' from the candidate catalog "
            "(routing guard: composer must not dispatch to itself)"
        )

    def test_validate_plan_uses_exit_code(self, lib_data: dict) -> None:
        evaluate = lib_data["fragments"]["validate_plan"].get("evaluate", {})
        assert evaluate.get("type") == "exit_code", (
            "validate_plan fragment must use exit_code evaluator (non-LLM evaluator requirement)"
        )

    def test_present_plan_is_prompt_type(self, lib_data: dict) -> None:
        assert lib_data["fragments"]["present_plan"].get("action_type") == "prompt"

    def test_present_plan_uses_cancel_pattern(self, lib_data: dict) -> None:
        evaluate = lib_data["fragments"]["present_plan"].get("evaluate", {})
        assert evaluate.get("pattern") == "CANCEL", (
            "present_plan fragment must detect CANCEL to abort execution"
        )

    def test_lib_has_reassess_fragment(self, lib_data: dict) -> None:
        assert "reassess" in lib_data["fragments"], (
            "lib/composer.yaml must define a 'reassess' fragment for the adaptive variant (FEAT-1983)"
        )

    def test_reassess_fragment_uses_llm_structured_evaluate(self, lib_data: dict) -> None:
        fragment = lib_data["fragments"]["reassess"]
        evaluate = fragment.get("evaluate", {})
        assert evaluate.get("type") == "llm_structured", (
            "reassess fragment must use llm_structured evaluate (pairs with output_numeric in MR-1 chain)"
        )

    def test_reassess_fragment_captures_reassess_decision(self, lib_data: dict) -> None:
        fragment = lib_data["fragments"]["reassess"]
        assert fragment.get("capture") == "reassess_decision"

    def test_reassess_fragment_action_is_prompt(self, lib_data: dict) -> None:
        fragment = lib_data["fragments"]["reassess"]
        assert fragment.get("action_type") == "prompt"

    def test_reassess_fragment_contains_decision_tokens(self, lib_data: dict) -> None:
        action = lib_data["fragments"]["reassess"].get("action", "")
        for token in ("CONTINUE", "REPLAN_TAIL", "ABORT"):
            assert token in action, (
                f"reassess fragment action must mention decision token {token!r}"
            )

    def test_discover_loops_fragment_excludes_adaptive_composer(self, lib_data: dict) -> None:
        action = lib_data["fragments"]["discover_loops"].get("action", "")
        assert "loop-composer-adaptive" in action, (
            "discover_loops fragment must exclude 'loop-composer-adaptive' from the candidate catalog"
        )

    def test_discover_loops_fragment_excludes_goal_cluster(self, lib_data: dict) -> None:
        action = lib_data["fragments"]["discover_loops"].get("action", "")
        assert "goal-cluster" in action, (
            "discover_loops fragment must exclude 'goal-cluster' from the candidate catalog"
        )

    def test_discover_loops_fragment_handles_include_allowlist(self, lib_data: dict) -> None:
        action = lib_data["fragments"]["discover_loops"].get("action", "")
        assert "_matches_include" in action, (
            "discover_loops fragment must define _matches_include filter for the include allowlist"
        )
        assert "category:" in action, (
            "discover_loops fragment include filter must support category:<label> selector form"
        )
        assert "builtin:*" in action, (
            "discover_loops fragment include filter must support builtin:* selector form"
        )
        assert "project:*" in action, (
            "discover_loops fragment include filter must support project:* selector form"
        )

    def test_discover_loops_fragment_uses_visibility_public(self, lib_data: dict) -> None:
        action = lib_data["fragments"]["discover_loops"].get("action", "")
        assert "--visibility public" in action, (
            "discover_loops fragment must include '--visibility public' flag on ll-loop list"
        )


class TestCatalogExclusivity:
    """Tests for the routing guard between loop-router, loop-composer, and goal-cluster."""

    @pytest.fixture
    def router_data(self) -> dict:
        assert ROUTER_FILE.exists(), f"loop-router.yaml not found at {ROUTER_FILE}"
        with open(ROUTER_FILE) as f:
            return yaml.safe_load(f)

    def test_loop_router_excludes_composer(self, router_data: dict) -> None:
        """loop-router must exclude loop-composer from its catalog discovery.

        Routing guard: loop-router and loop-composer are at the same orchestration
        level. loop-router must not present loop-composer as a candidate for a goal
        that could be handled by a single existing loop.
        """
        action = router_data.get("states", {}).get("discover_loops", {}).get("action", "")
        assert "loop-composer" in action, (
            "loop-router's discover_loops must add loop-composer to excludes "
            "(wiring step 8 from FEAT-1808 spec)"
        )

    def test_loop_composer_discover_imports_lib(self) -> None:
        """loop-composer imports lib/composer.yaml which excludes both loop-router and loop-composer."""
        with open(LOOP_FILE) as f:
            data = yaml.safe_load(f)
        assert "lib/composer.yaml" in data.get("import", [])

    def test_loop_router_excludes_adaptive_composer(self, router_data: dict) -> None:
        """loop-router must exclude loop-composer-adaptive from its catalog discovery."""
        action = router_data.get("states", {}).get("discover_loops", {}).get("action", "")
        assert "loop-composer-adaptive" in action, (
            "loop-router's discover_loops must add loop-composer-adaptive to excludes "
            "(wiring step 9 from FEAT-1983 spec)"
        )

    def test_loop_router_excludes_goal_cluster(self, router_data: dict) -> None:
        """loop-router must exclude goal-cluster from its catalog discovery."""
        action = router_data.get("states", {}).get("discover_loops", {}).get("action", "")
        assert "goal-cluster" in action, (
            "loop-router's discover_loops must add goal-cluster to excludes "
            "(wiring step from FEAT-1988 spec)"
        )


class TestValidatePlanFragmentExecution:
    """Functional tests that actually run the validate_plan fragment Python body.

    Regression coverage for the composer audit (2026-06-13): the fragment used to
    interpolate ${captured.catalog.output} into a single-quoted Python string literal,
    which crashed with a SyntaxError on every invocation because the catalog JSON is
    multi-line and contains embedded quotes. The fix reads the catalog from disk
    (composer-catalog.json) instead. These tests execute the fragment to ensure it
    parses and validates correctly, not just that the YAML has the right shape.
    """

    @pytest.fixture
    def lib_data(self) -> dict:
        with open(LIB_FILE) as f:
            return yaml.safe_load(f)

    def _extract_python_body(self, action: str) -> str:
        """Pull the heredoc Python body out of a `python3 << 'PYEOF' ... PYEOF` action."""
        lines = action.splitlines()
        start = next(i for i, ln in enumerate(lines) if "<< 'PYEOF'" in ln)
        end = next(i for i in range(start + 1, len(lines)) if lines[i].strip() == "PYEOF")
        return "\n".join(lines[start + 1 : end])

    def _run_validate_plan(
        self, lib_data: dict, tmp_path: Path, catalog: dict, plan: list, max_nodes: int = 8
    ):
        import subprocess
        import sys

        run_dir = tmp_path / "run"
        run_dir.mkdir()
        (run_dir / "composer-catalog.json").write_text(__import__("json").dumps(catalog))
        (run_dir / "composer-plan.json").write_text(__import__("json").dumps(plan))

        body = self._extract_python_body(lib_data["fragments"]["validate_plan"]["action"])
        body = body.replace("${context.run_dir}", str(run_dir))
        body = body.replace("${context.max_plan_nodes}", str(max_nodes))
        script = tmp_path / "validate_plan.py"
        script.write_text(body)
        return subprocess.run(
            [sys.executable, str(script)], capture_output=True, text=True
        ), run_dir

    def test_fragment_does_not_interpolate_catalog_into_string_literal(
        self, lib_data: dict
    ) -> None:
        """Guard the anti-pattern that caused the original SyntaxError."""
        action = lib_data["fragments"]["validate_plan"]["action"]
        assert "'${captured.catalog.output}'" not in action, (
            "validate_plan must NOT interpolate the multi-line catalog JSON into a "
            "string literal — read composer-catalog.json from disk instead (audit 2026-06-13)"
        )
        assert "composer-catalog.json" in action, (
            "validate_plan must read the catalog from disk via composer-catalog.json"
        )

    def test_valid_plan_exits_zero_and_writes_topo_order(
        self, lib_data: dict, tmp_path: Path
    ) -> None:
        catalog = {
            "project": [{"name": "loop-a"}, {"name": "loop-b"}],
            "builtin": [{"name": "loop-router"}],
        }
        plan = [
            {"step_id": "s1", "loop_name": "loop-a", "input": "x", "depends_on": []},
            {"step_id": "s2", "loop_name": "loop-b", "input": "y", "depends_on": ["s1"]},
        ]
        result, run_dir = self._run_validate_plan(lib_data, tmp_path, catalog, plan)
        assert result.returncode == 0, f"valid plan should pass: {result.stdout}\n{result.stderr}"
        assert "PLAN_VALID" in result.stdout
        assert (run_dir / "topo-order.json").exists()

    def test_unknown_loop_name_is_rejected_via_disk_catalog(
        self, lib_data: dict, tmp_path: Path
    ) -> None:
        """The catalog-read fix must still enforce the unknown-loop-name check."""
        catalog = {"project": [{"name": "loop-a"}], "builtin": []}
        plan = [{"step_id": "s1", "loop_name": "does-not-exist", "input": "x", "depends_on": []}]
        result, _ = self._run_validate_plan(lib_data, tmp_path, catalog, plan)
        assert result.returncode == 1
        assert "not in catalog" in result.stdout

    def test_catalog_with_quotes_and_newlines_does_not_crash(
        self, lib_data: dict, tmp_path: Path
    ) -> None:
        """The exact failure mode from the audit: descriptions with quotes/newlines."""
        catalog = {
            "project": [
                {
                    "name": "loop-a",
                    "description": "has 'single' and \"double\" quotes\nand a newline",
                }
            ],
            "builtin": [],
        }
        plan = [{"step_id": "s1", "loop_name": "loop-a", "input": "x", "depends_on": []}]
        result, _ = self._run_validate_plan(lib_data, tmp_path, catalog, plan)
        assert result.returncode == 0, f"catalog with quotes must not crash: {result.stderr}"
        assert "SyntaxError" not in result.stderr


@pytest.mark.slow
@pytest.mark.skipif(shutil.which("claude") is None, reason="claude CLI not available")
class TestLoopComposerLive:
    """Live-LLM tests for loop-composer (marked slow, requires claude CLI)."""

    def test_loop_validates_before_live_run(self) -> None:
        fsm, _ = load_and_validate(LOOP_FILE)
        errors = validate_fsm(fsm)
        error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        assert not error_list, (
            f"loop-composer must validate cleanly before any live run: {[str(e) for e in error_list]}"
        )
