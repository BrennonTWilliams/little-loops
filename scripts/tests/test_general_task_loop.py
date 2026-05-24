"""Tests for the general-task built-in loop (ENH-1644).

Guards the four coordinated edits to ``scripts/little_loops/loops/general-task.yaml``
against regression via prompt-content assertions:

- Change 1: ``define_done.action`` requires runtime-verification criteria.
- Change 2: ``check_done.action`` reads both DoD and plan and emits a sample-verify section.
- Change 3: ``continue_work.action`` adds a remediation plan step when plan is fully [x].
- Change 4: ``check_done.evaluate.prompt`` confirms three structural conditions.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from little_loops.fsm.validation import ValidationSeverity, load_and_validate, validate_fsm

BUILTIN_LOOPS_DIR = Path(__file__).parent.parent / "little_loops" / "loops"
LOOP_FILE = BUILTIN_LOOPS_DIR / "general-task.yaml"


@pytest.fixture
def raw_data() -> dict:
    """Load the general-task YAML before any inheritance/fragment resolution."""
    assert LOOP_FILE.exists(), f"general-task.yaml not found at {LOOP_FILE}"
    with open(LOOP_FILE) as f:
        return yaml.safe_load(f)


class TestGeneralTaskLoopFile:
    """Structural tests for general-task.yaml."""

    def test_file_exists(self) -> None:
        assert LOOP_FILE.exists(), f"general-task.yaml not found at {LOOP_FILE}"

    def test_parses_as_yaml(self, raw_data: dict) -> None:
        assert isinstance(raw_data, dict)

    def test_validates_as_fsm(self) -> None:
        fsm, _ = load_and_validate(LOOP_FILE)
        errors = validate_fsm(fsm)
        error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        assert not error_list, f"FSM validation errors: {[str(e) for e in error_list]}"

    def test_name(self, raw_data: dict) -> None:
        assert raw_data.get("name") == "general-task"

    def test_expected_states_present(self, raw_data: dict) -> None:
        states = raw_data.get("states", {})
        expected = {
            "define_done",
            "plan",
            "execute",
            "check_done",
            "continue_work",
            "done",
            "diagnose",
            "failed",
        }
        assert expected.issubset(set(states.keys())), (
            f"Missing states: {expected - set(states.keys())}"
        )


class TestChange1DefineDoneRuntimeCriteria:
    """Change 1: define_done.action requires runtime-verification criteria."""

    def test_define_done_action_requires_runtime_criteria(self, raw_data: dict) -> None:
        action = raw_data["states"]["define_done"]["action"]
        # The prompt must explicitly demand runtime criteria for runtime-surface tasks.
        assert "runtime" in action.lower(), (
            "define_done.action must mention runtime-verification criteria"
        )
        # Must call out that static checks alone are insufficient.
        assert "static" in action.lower() and "insufficient" in action.lower(), (
            "define_done.action must state that static checks alone are insufficient "
            "when the task has a runtime surface"
        )


class TestChange2CheckDoneReconcileAndSampleVerify:
    """Change 2: check_done.action reads both files, reconciles, and sample-verifies."""

    def test_check_done_reads_both_dod_and_plan(self, raw_data: dict) -> None:
        action = raw_data["states"]["check_done"]["action"]
        assert "general-task-dod.md" in action, (
            "check_done.action must reference the DoD file"
        )
        assert "general-task-plan.md" in action, (
            "check_done.action must reference the plan file"
        )

    def test_check_done_does_plan_vs_dod_coverage(self, raw_data: dict) -> None:
        action = raw_data["states"]["check_done"]["action"]
        # Must do plan-vs-DoD coverage reconciliation: every plan step needs DoD coverage.
        assert "coverage" in action.lower() or "covers" in action.lower(), (
            "check_done.action must reconcile plan-vs-DoD coverage"
        )
        # Must add a new criterion for any plan step without DoD coverage.
        assert "ADD a new criterion" in action or "add a new criterion" in action.lower(), (
            "check_done.action must add new DoD criteria for uncovered plan steps"
        )

    def test_check_done_emits_sample_verification_section(self, raw_data: dict) -> None:
        action = raw_data["states"]["check_done"]["action"]
        assert "## Sample Verification" in action, (
            "check_done.action must append a `## Sample Verification` section to the DoD"
        )
        # Must independently re-verify up to min(3, total_checked) already-[x] criteria.
        assert "min(3" in action or "up to 3" in action.lower(), (
            "check_done.action must sample up to 3 already-[x] criteria for re-verification"
        )


class TestChange3ContinueWorkDodFallback:
    """Change 3: continue_work.action falls back to DoD-remediation when plan is fully [x]."""

    def test_continue_work_reads_both_files(self, raw_data: dict) -> None:
        action = raw_data["states"]["continue_work"]["action"]
        assert "general-task-plan.md" in action and "general-task-dod.md" in action, (
            "continue_work.action must read both plan and DoD files"
        )

    def test_continue_work_has_remediation_fallback(self, raw_data: dict) -> None:
        action = raw_data["states"]["continue_work"]["action"]
        # Must append a remediation plan step when plan is fully [x] but DoD has unchecked criteria.
        assert "remediation" in action.lower() or "APPEND" in action, (
            "continue_work.action must append a remediation step when plan is fully [x] "
            "but a DoD criterion remains unchecked"
        )

    def test_continue_work_diverges_from_execute(self, raw_data: dict) -> None:
        """continue_work.action must no longer be a verbatim duplicate of execute.action."""
        execute_action = raw_data["states"]["execute"]["action"]
        continue_action = raw_data["states"]["continue_work"]["action"]
        assert execute_action.strip() != continue_action.strip(), (
            "continue_work.action must diverge from execute.action (Change 3)"
        )


class TestChange4CheckDoneEvaluatorStructural:
    """Change 4: check_done.evaluate.prompt confirms three structural conditions."""

    def test_evaluator_is_llm_structured(self, raw_data: dict) -> None:
        evaluate = raw_data["states"]["check_done"]["evaluate"]
        assert evaluate["type"] == "llm_structured"

    def test_evaluator_prompt_references_three_conditions(self, raw_data: dict) -> None:
        prompt = raw_data["states"]["check_done"]["evaluate"]["prompt"]
        # Three structural conditions: DoD all [x], plan all [x], sample-verify clean.
        assert "(1)" in prompt and "(2)" in prompt and "(3)" in prompt, (
            "evaluator prompt must enumerate three structural conditions"
        )
        # DoD condition
        assert "DoD" in prompt or "Verification Criteria" in prompt, (
            "evaluator prompt must check the DoD"
        )
        # Plan condition
        assert "plan" in prompt.lower() and "[x]" in prompt, (
            "evaluator prompt must check that plan steps are [x]"
        )
        # Sample Verification condition
        assert "Sample Verification" in prompt, (
            "evaluator prompt must check the `## Sample Verification` section"
        )

    def test_evaluator_routes_yes_to_done_no_to_continue(self, raw_data: dict) -> None:
        check_done = raw_data["states"]["check_done"]
        assert check_done["on_yes"] == "done"
        assert check_done["on_no"] == "continue_work"


class TestChange5ExecuteCapture:
    """Change 5 (ENH-1671): execute state captures output for check_done delta input."""

    def test_execute_has_capture_execute_result(self, raw_data: dict) -> None:
        execute_state = raw_data["states"]["execute"]
        assert execute_state.get("capture") == "execute_result", (
            "execute state must have capture: execute_result so check_done can read the delta"
        )

    def test_execute_prompts_for_last_step_output(self, raw_data: dict) -> None:
        action = raw_data["states"]["execute"]["action"]
        assert "LAST_STEP" in action, (
            "execute.action must instruct the model to emit a LAST_STEP: trailing line"
        )

    def test_execute_prompts_for_last_files_output(self, raw_data: dict) -> None:
        action = raw_data["states"]["execute"]["action"]
        assert "LAST_FILES" in action, (
            "execute.action must instruct the model to emit a LAST_FILES: trailing line"
        )


class TestChange6CheckDoneDeltaAware:
    """Change 6 (ENH-1671): check_done.action scopes verification to the most recent step."""

    def test_check_done_references_captured_execute_result(self, raw_data: dict) -> None:
        action = raw_data["states"]["check_done"]["action"]
        assert "${captured.execute_result.output}" in action, (
            "check_done.action must reference ${captured.execute_result.output} for delta context"
        )

    def test_check_done_references_last_step(self, raw_data: dict) -> None:
        action = raw_data["states"]["check_done"]["action"]
        assert "LAST_STEP" in action, (
            "check_done.action must reference LAST_STEP from captured execute output"
        )

    def test_check_done_references_last_files(self, raw_data: dict) -> None:
        action = raw_data["states"]["check_done"]["action"]
        assert "LAST_FILES" in action, (
            "check_done.action must reference LAST_FILES from captured execute output"
        )

    def test_check_done_has_plausibly_affected_scoping(self, raw_data: dict) -> None:
        action = raw_data["states"]["check_done"]["action"]
        assert "plausibly affected" in action.lower(), (
            "check_done.action must use 'plausibly affected' language to describe the scoping policy"
        )


class TestChange6SampleVerificationPreserved:
    """Change 6 (ENH-1671): sample re-verification safety net is unchanged after delta rewrite."""

    def test_check_done_still_has_sample_verification_section(self, raw_data: dict) -> None:
        action = raw_data["states"]["check_done"]["action"]
        assert "## Sample Verification" in action, (
            "check_done.action must still append a `## Sample Verification` section"
        )

    def test_check_done_still_uses_min3_sample_size(self, raw_data: dict) -> None:
        action = raw_data["states"]["check_done"]["action"]
        assert "min(3" in action or "up to 3" in action.lower(), (
            "check_done.action must still sample up to min(3, total_checked) criteria"
        )
