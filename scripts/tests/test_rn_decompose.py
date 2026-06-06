"""Tests for the rn-decompose sub-loop (extracted from rn-implement Phase 5)."""

from __future__ import annotations

from pathlib import Path

import yaml

from little_loops.fsm import is_runnable_loop
from little_loops.fsm.validation import load_and_validate

LOOPS_DIR = Path(__file__).parent.parent / "little_loops" / "loops"
RN_DECOMPOSE_PATH = LOOPS_DIR / "rn-decompose.yaml"


def _load_loop() -> dict:
    """Load the rn-decompose YAML file."""
    with open(RN_DECOMPOSE_PATH) as f:
        return yaml.safe_load(f)


# ============================================================================
# TestDecompositionChain — States: snap_for_size_review → run_size_review →
# detect_children → enqueue_children
# ============================================================================


class TestDecompositionChain:
    """Tests for the decomposition path (size review → child detection → enqueue)."""

    def test_snap_for_size_review_snapshots_issues(self) -> None:
        """snap_for_size_review snapshots ll-issues list --json output."""
        data = _load_loop()
        snap = data["states"]["snap_for_size_review"]
        action = snap["action"]
        assert "ll-issues list --json" in action
        assert "issues_before_" in action

    def test_snap_for_size_review_uses_context_issue_id(self) -> None:
        """snap_for_size_review references ${context.issue_id} (standalone sub-loop pattern)."""
        data = _load_loop()
        snap = data["states"]["snap_for_size_review"]
        action = snap["action"]
        assert "${context.issue_id}" in action

    def test_snap_for_size_review_uses_context_run_dir(self) -> None:
        """snap_for_size_review references ${context.run_dir} (standalone sub-loop pattern)."""
        data = _load_loop()
        snap = data["states"]["snap_for_size_review"]
        action = snap["action"]
        assert "${context.run_dir}" in action

    def test_snap_for_size_review_routes_to_run_size_review(self) -> None:
        """snap_for_size_review always transitions to run_size_review."""
        data = _load_loop()
        snap = data["states"]["snap_for_size_review"]
        assert snap["next"] == "run_size_review"

    def test_snap_for_size_review_errors_to_failed(self) -> None:
        """snap_for_size_review routes on_error to failed (sub-loop terminal)."""
        data = _load_loop()
        snap = data["states"]["snap_for_size_review"]
        assert snap["on_error"] == "emit_size_review_failed"

    def test_run_size_review_is_slash_command(self) -> None:
        """run_size_review invokes /ll:issue-size-review as slash_command."""
        data = _load_loop()
        rsr = data["states"]["run_size_review"]
        assert rsr["action_type"] == "slash_command"
        assert "/ll:issue-size-review" in rsr["action"]

    def test_run_size_review_wraps_with_rate_limit_handling(self) -> None:
        """run_size_review uses with_rate_limit_handling fragment."""
        data = _load_loop()
        rsr = data["states"]["run_size_review"]
        assert rsr.get("fragment") == "with_rate_limit_handling"

    def test_run_size_review_has_rate_limit_exhausted_handler(self) -> None:
        """run_size_review preserves on_rate_limit_exhausted → rate_limit_diagnostic (BUG-1937)."""
        data = _load_loop()
        rsr = data["states"]["run_size_review"]
        assert rsr.get("on_rate_limit_exhausted") == "rate_limit_diagnostic", (
            "BUG-1937: on_rate_limit_exhausted must carry over to sub-loop"
        )

    def test_run_size_review_routes_partial_to_detect_children(self) -> None:
        """run_size_review routes on_partial to detect_children (BUG-1975)."""
        data = _load_loop()
        rsr = data["states"]["run_size_review"]
        assert rsr.get("on_partial") == "detect_children", (
            "BUG-1975: a partial LLM verdict (e.g. hygiene caveat) must proceed to "
            "detect_children, not error-terminate the sub-loop"
        )

    def test_run_size_review_errors_to_failed(self) -> None:
        """run_size_review routes on_error to failed (sub-loop terminal)."""
        data = _load_loop()
        rsr = data["states"]["run_size_review"]
        assert rsr["on_error"] == "emit_size_review_failed"

    def test_detect_children_uses_comm_diff(self) -> None:
        """detect_children uses comm -13 for pre/post diff."""
        data = _load_loop()
        dc = data["states"]["detect_children"]
        action = dc["action"]
        assert "comm -13" in action

    def test_detect_children_filters_by_parent_reference(self) -> None:
        """detect_children filters candidates by parent ref in issue files."""
        data = _load_loop()
        dc = data["states"]["detect_children"]
        action = dc["action"]
        assert "parent:" in action or "Decomposed from" in action

    def test_detect_children_routes_yes_to_enqueue_children(self) -> None:
        """detect_children routes to enqueue_children when children found."""
        data = _load_loop()
        dc = data["states"]["detect_children"]
        assert dc["on_yes"] == "enqueue_children"

    def test_detect_children_routes_no_to_done(self) -> None:
        """detect_children routes to done when no children found (expected success path, BUG-1974)."""
        data = _load_loop()
        dc = data["states"]["detect_children"]
        # ENH-1977 Fix 1: routes via emit_no_children, which still terminates in
        # `done` (preserving the BUG-1974 telemetry guarantee) after writing the
        # NO_CHILDREN outcome token for the parent classifier.
        assert dc["on_no"] == "emit_no_children"
        assert data["states"]["emit_no_children"]["next"] == "done", (
            "BUG-1974: no-children must still terminate in done, not failed"
        )

    def test_detect_children_errors_to_failed(self) -> None:
        """detect_children routes on_error to failed (sub-loop terminal)."""
        data = _load_loop()
        dc = data["states"]["detect_children"]
        assert dc["on_error"] == "emit_size_review_failed"

    def test_description_does_not_misclassify_no_children_as_failed(self) -> None:
        """Loop description must not say 'no children found' terminates in failed (BUG-1974)."""
        data = _load_loop()
        description = data.get("description", "")
        assert "no children found" not in description.lower() or "failed" not in description.lower(), (
            "BUG-1974: description still classifies 'no children found' as a failed outcome"
        )

    def test_enqueue_children_has_cycle_detection(self) -> None:
        """enqueue_children performs cycle detection via Python visited set."""
        data = _load_loop()
        ec = data["states"]["enqueue_children"]
        action = ec["action"]
        assert "visited" in action.lower()
        assert "cycles.txt" in action

    def test_enqueue_children_prepends_depth_first(self) -> None:
        """enqueue_children prepends children before existing queue (depth-first)."""
        data = _load_loop()
        ec = data["states"]["enqueue_children"]
        action = ec["action"]
        assert 'echo "$CHILDREN"' in action
        assert 'echo "$EXISTING"' in action

    def test_enqueue_children_routes_to_done(self) -> None:
        """enqueue_children routes both outcomes to done (sub-loop terminal)."""
        data = _load_loop()
        ec = data["states"]["enqueue_children"]
        # ENH-1977 Fix 4: success now routes through finalize_parent (which closes
        # the decomposed parent and terminates in done); the cycle-filtered path
        # emits NO_CHILDREN and terminates in done.
        assert ec["on_yes"] == "finalize_parent"
        assert data["states"]["finalize_parent"]["next"] == "done"
        assert ec["on_no"] == "emit_no_children"

    def test_enqueue_children_errors_to_failed(self) -> None:
        """enqueue_children routes on_error to failed (sub-loop terminal)."""
        data = _load_loop()
        ec = data["states"]["enqueue_children"]
        assert ec["on_error"] == "emit_size_review_failed"


# ============================================================================
# TestCycleDetection — State: enqueue_children (cycle detection logic)
# ============================================================================


class TestCycleDetection:
    """Tests for cycle detection in enqueue_children."""

    def test_enqueue_children_checks_visited_before_enqueue(self) -> None:
        """enqueue_children reads visited.txt before enqueuing candidates."""
        data = _load_loop()
        ec = data["states"]["enqueue_children"]
        action = ec["action"]
        assert "visited.txt" in action

    def test_cycle_candidates_logged_to_cycles_txt(self) -> None:
        """Cycle-detected IDs are logged to cycles.txt."""
        data = _load_loop()
        ec = data["states"]["enqueue_children"]
        action = ec["action"]
        assert "cycles.txt" in action

    def test_enqueue_children_includes_queue_in_visited_set(self) -> None:
        """enqueue_children builds visited set from visited.txt + queue.txt."""
        data = _load_loop()
        ec = data["states"]["enqueue_children"]
        action = ec["action"]
        assert "queue.txt" in action, "Must include current queue in visited set"


# ============================================================================
# TestParameterContract
# ============================================================================


class TestParameterContract:
    """Tests for the parameters block."""

    def test_parameters_block_exists(self) -> None:
        """parameters block is declared."""
        data = _load_loop()
        assert "parameters" in data

    def test_issue_id_is_required_string(self) -> None:
        """issue_id parameter is required and type string."""
        data = _load_loop()
        params = data["parameters"]
        assert "issue_id" in params
        assert params["issue_id"]["type"] == "string"
        assert params["issue_id"]["required"] is True

    def test_parent_depth_is_optional_integer(self) -> None:
        """parent_depth parameter is optional with default 0."""
        data = _load_loop()
        params = data["parameters"]
        assert "parent_depth" in params
        assert params["parent_depth"]["type"] == "integer"
        assert params["parent_depth"]["required"] is False

    def test_run_dir_is_required_path(self) -> None:
        """run_dir parameter is required and type path."""
        data = _load_loop()
        params = data["parameters"]
        assert "run_dir" in params
        assert params["run_dir"]["type"] == "path"
        assert params["run_dir"]["required"] is True

    def test_parent_depth_default_in_context(self) -> None:
        """parent_depth default of 0 is provided via context block."""
        data = _load_loop()
        ctx = data.get("context", {})
        assert ctx.get("parent_depth") == 0


# ============================================================================
# TestTerminalStates
# ============================================================================


class TestTerminalStates:
    """Tests for terminal states: done, failed."""

    def test_done_is_bare_terminal(self) -> None:
        """done state has terminal: true and no action."""
        data = _load_loop()
        done = data["states"]["done"]
        assert done.get("terminal") is True
        assert "action" not in done
        assert "action_type" not in done

    def test_failed_is_bare_terminal(self) -> None:
        """failed state has terminal: true and no action."""
        data = _load_loop()
        failed = data["states"]["failed"]
        assert failed.get("terminal") is True
        assert "action" not in failed
        assert "action_type" not in failed

    def test_terminal_states_have_no_outgoing_routes(self) -> None:
        """Bare terminal states have no routing keys."""
        data = _load_loop()
        routing_keys = ("next", "on_yes", "on_no", "on_error", "on_success", "on_failure")
        for state_name in ("done", "failed"):
            state = data["states"][state_name]
            for key in routing_keys:
                assert key not in state, f"{state_name} should not have '{key}'"


# ============================================================================
# TestTopLevelDeclarations
# ============================================================================


class TestTopLevelDeclarations:
    """Tests for top-level declarations: name, import, on_handoff."""

    def test_name_is_rn_decompose(self) -> None:
        """Loop name is rn-decompose."""
        data = _load_loop()
        assert data["name"] == "rn-decompose"

    def test_imports_lib_common_yaml(self) -> None:
        """Imports lib/common.yaml for shared fragments."""
        data = _load_loop()
        assert "lib/common.yaml" in data.get("import", [])

    def test_on_handoff_is_spawn(self) -> None:
        """on_handoff is spawn (required for sub-loop spawning)."""
        data = _load_loop()
        assert data.get("on_handoff") == "spawn"

    def test_category_is_planning(self) -> None:
        """Category is planning (matches sibling rn-remediate)."""
        data = _load_loop()
        assert data.get("category") == "planning"

    def test_initial_state_is_snap_for_size_review(self) -> None:
        """Initial state is snap_for_size_review."""
        data = _load_loop()
        assert data["initial"] == "snap_for_size_review"


# ============================================================================
# TestFSMHealth — Structural validation
# ============================================================================


class TestFSMHealth:
    """Structural validation tests for the rn-decompose FSM."""

    def test_fsm_validates_without_errors(self) -> None:
        """rn-decompose.yaml passes ll-loop validate with no errors."""
        fsm, warnings = load_and_validate(RN_DECOMPOSE_PATH)
        assert fsm is not None, "FSM must load and validate successfully"

    def test_is_runnable_loop(self) -> None:
        """rn-decompose is recognized as a runnable loop."""
        assert is_runnable_loop(RN_DECOMPOSE_PATH), (
            "rn-decompose.yaml must be recognized as a runnable loop"
        )

    def test_mr1_non_llm_evaluators_present(self) -> None:
        """All LLM-invoking states are paired with non-LLM evaluators (MR-1)."""
        data = _load_loop()

        # run_size_review is slash_command with with_rate_limit_handling fragment
        # → non-LLM evaluator = fragment's exit_code check via harness
        rsr = data["states"]["run_size_review"]
        assert rsr.get("fragment") == "with_rate_limit_handling"

        # detect_children uses shell_exit fragment → evaluated by exit_code
        dc = data["states"]["detect_children"]
        assert dc.get("fragment") == "shell_exit"

    def test_mr3_run_dir_used_for_writes(self) -> None:
        """No state writes to .loops/tmp/ — all file writes use ${context.run_dir}/."""
        data = _load_loop()
        for name, state in data["states"].items():
            action = state.get("action", "")
            if isinstance(action, str):
                assert ".loops/tmp/" not in action, (
                    f"State '{name}' writes to .loops/tmp/ — use ${{context.run_dir}}/"
                )

    def test_all_states_reachable_from_initial(self) -> None:
        """All states are reachable from the initial state."""
        data = _load_loop()
        state_names = set(data["states"].keys())
        routing_keys = (
            "next",
            "on_yes",
            "on_no",
            "on_partial",
            "on_error",
            "on_success",
            "on_failure",
            "on_rate_limit_exhausted",
        )
        reachable: set[str] = set()
        queue = [data["initial"]]
        while queue:
            current = queue.pop(0)
            if current in reachable or current not in data["states"]:
                continue
            reachable.add(current)
            state = data["states"][current]
            for key in routing_keys:
                target = state.get(key)
                if target and isinstance(target, str) and target not in reachable:
                    queue.append(target)
        unreachable = state_names - reachable
        assert not unreachable, f"Unreachable states: {unreachable}"

    def test_all_referenced_targets_exist(self) -> None:
        """All routing targets reference existing states."""
        data = _load_loop()
        state_names = set(data["states"].keys())
        routing_keys = (
            "next",
            "on_yes",
            "on_no",
            "on_partial",
            "on_error",
            "on_success",
            "on_failure",
            "on_rate_limit_exhausted",
        )
        for name, state in data["states"].items():
            for key in routing_keys:
                target = state.get(key)
                if target and isinstance(target, str):
                    assert target in state_names, (
                        f"State '{name}' {key} references non-existent '{target}'"
                    )

    def test_no_dead_end_states(self) -> None:
        """No non-terminal states are dead-ends."""
        data = _load_loop()
        for name, state in data["states"].items():
            if state.get("terminal"):
                continue
            if "next" in state:
                continue
            has_route = any(
                k in state for k in ("on_yes", "on_no", "on_success", "on_failure", "on_error")
            )
            assert has_route, f"State '{name}' is a dead-end (no outgoing routes)"


# ============================================================================
# TestDecomposeOutcomeChannel — ENH-1977 Fix 1/4 (rn-decompose side)
# ============================================================================


class TestDecomposeOutcomeChannel:
    """rn-decompose writes outcome tokens and finalizes the decomposed parent."""

    def test_emit_states_exist(self) -> None:
        data = _load_loop()
        for name in ("emit_no_children", "emit_size_review_failed", "finalize_parent"):
            assert name in data["states"], f"missing state {name}"

    def test_finalize_parent_writes_decomposed_and_calls_cli(self) -> None:
        data = _load_loop()
        fp = data["states"]["finalize_parent"]
        assert "DECOMPOSED" in fp["action"]
        assert "ll-issues finalize-decomposition" in fp["action"]
        assert fp["next"] == "done"

    def test_enqueue_children_routes_to_finalize_parent(self) -> None:
        data = _load_loop()
        assert data["states"]["enqueue_children"]["on_yes"] == "finalize_parent"

    def test_emit_no_children_token_and_done(self) -> None:
        data = _load_loop()
        s = data["states"]["emit_no_children"]
        assert "NO_CHILDREN" in s["action"]
        assert s["next"] == "done"

    def test_emit_size_review_failed_token_and_failed(self) -> None:
        data = _load_loop()
        s = data["states"]["emit_size_review_failed"]
        assert "SIZE_REVIEW_FAILED" in s["action"]
        assert s["next"] == "failed"

    def test_detect_children_no_children_emits_token(self) -> None:
        data = _load_loop()
        assert data["states"]["detect_children"]["on_no"] == "emit_no_children"

    def test_rate_limit_diagnostic_writes_token_and_fails(self) -> None:
        data = _load_loop()
        rld = data["states"]["rate_limit_diagnostic"]
        assert "RATE_LIMITED" in rld["action"]
        assert rld["next"] == "failed"

    def test_detect_children_matches_body_marker(self) -> None:
        """Detection survives the parent: repoint via the Decomposed-from marker (Fix 4)."""
        data = _load_loop()
        assert "Decomposed from" in data["states"]["detect_children"]["action"]
