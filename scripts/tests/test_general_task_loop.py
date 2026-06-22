"""Tests for the general-task built-in loop (ENH-1644).

Guards the four coordinated edits to ``scripts/little_loops/loops/general-task.yaml``
against regression via prompt-content assertions:

- Change 1: ``define_done.action`` requires runtime-verification criteria.
- Change 2: ``check_done.action`` reads both DoD and plan and emits a sample-verify section.
- Change 3: ``continue_work.action`` adds a remediation plan step when plan is fully [x].
- Change 4: ``check_done.evaluate.prompt`` confirms three structural conditions.
"""

from __future__ import annotations

import subprocess
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
            "select_step",
            "do_work",
            "verify_step",
            "mark_done",
            "check_done",
            "count_done",
            "final_verify",
            "count_final",
            "continue_work",
            "done",
            "diagnose",
            "failed",
            "summarize_partial",
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
        assert "dod.md" in action, "check_done.action must reference the DoD file"
        assert "plan.md" in action, "check_done.action must reference the plan file"

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
            "check_done.action must reference the `## Sample Verification` section in the DoD"
        )
        # Must independently re-verify up to min(3, total_checked) already-[x] criteria.
        assert "min(3" in action or "up to 3" in action.lower(), (
            "check_done.action must sample up to 3 already-[x] criteria for re-verification"
        )

    def test_check_done_replaces_not_appends_sample_verification(self, raw_data: dict) -> None:
        action = raw_data["states"]["check_done"]["action"]
        action_lower = action.lower()
        assert "replace" in action_lower, (
            "check_done.action must instruct the agent to replace the `## Sample Verification` section"
        )
        # Must not instruct appending a new section (which causes unbounded accumulation).
        assert "append a" not in action_lower or "sample verification" not in action_lower, (
            "check_done.action must not instruct appending a new `## Sample Verification` section"
        )


class TestChange3ContinueWorkDodFallback:
    """Change 3: continue_work.action falls back to DoD-remediation when plan is fully [x]."""

    def test_continue_work_reads_both_files(self, raw_data: dict) -> None:
        action = raw_data["states"]["continue_work"]["action"]
        assert "plan.md" in action and "dod.md" in action, (
            "continue_work.action must read both plan and DoD files"
        )

    def test_continue_work_has_remediation_fallback(self, raw_data: dict) -> None:
        action = raw_data["states"]["continue_work"]["action"]
        # Must append a remediation plan step when plan is fully [x] but DoD has unchecked criteria.
        assert "remediation" in action.lower() or "APPEND" in action, (
            "continue_work.action must append a remediation step when plan is fully [x] "
            "but a DoD criterion remains unchecked"
        )


class TestChange7CountDoneShellGate:
    """Change 7 (ENH-1658): check_done routes to count_done shell gate; no llm_structured evaluator."""

    def test_check_done_has_no_evaluate_block(self, raw_data: dict) -> None:
        check_done = raw_data["states"]["check_done"]
        assert "evaluate" not in check_done, (
            "check_done must not have an evaluate block; the gate moved to count_done"
        )

    def test_check_done_routes_to_count_done(self, raw_data: dict) -> None:
        check_done = raw_data["states"]["check_done"]
        assert check_done.get("next") == "count_done", (
            "check_done must route unconditionally to count_done"
        )

    def test_count_done_action_type_is_shell(self, raw_data: dict) -> None:
        count_done = raw_data["states"]["count_done"]
        assert count_done["action_type"] == "shell"

    def test_count_done_evaluate_is_output_json(self, raw_data: dict) -> None:
        evaluate = raw_data["states"]["count_done"]["evaluate"]
        assert evaluate["type"] == "output_json"

    def test_count_done_evaluate_path_is_total(self, raw_data: dict) -> None:
        evaluate = raw_data["states"]["count_done"]["evaluate"]
        assert evaluate["path"] == ".total"

    def test_count_done_evaluate_operator_eq_zero(self, raw_data: dict) -> None:
        evaluate = raw_data["states"]["count_done"]["evaluate"]
        assert evaluate["operator"] == "eq"
        assert evaluate["target"] == 0

    def test_count_done_routes_yes_to_done(self, raw_data: dict) -> None:
        count_done = raw_data["states"]["count_done"]
        assert count_done["on_yes"] == "final_verify"

    def test_count_done_routes_no_to_continue_work(self, raw_data: dict) -> None:
        count_done = raw_data["states"]["count_done"]
        assert count_done["on_no"] == "continue_work"

    def test_count_done_routes_error_to_diagnose(self, raw_data: dict) -> None:
        count_done = raw_data["states"]["count_done"]
        assert count_done["on_error"] == "diagnose"

    def test_count_done_captures_done_counts(self, raw_data: dict) -> None:
        count_done = raw_data["states"]["count_done"]
        assert count_done.get("capture") == "done_counts"


class TestBUG1687ContinueWorkCapture:
    """BUG-1687 (superseded by ENH-1732): continue_work handles only DoD remediation (Case B).

    After ENH-1732, continue_work no longer captures execute_result or emits LAST_STEP/LAST_FILES.
    Step selection and implementation moved to select_step and do_work respectively.
    continue_work only appends a remediation plan step, then routes to select_step.
    """

    def test_continue_work_routes_to_select_step(self, raw_data: dict) -> None:
        state = raw_data["states"]["continue_work"]
        # Routing moved from an unconditional `next` to an evaluated branch so
        # continue_work can escape to final_verify when there is nothing to remediate.
        # The remediation path still goes to select_step (on_no) so the appended step
        # runs through the full select_step → do_work → verify_step → mark_done chain.
        assert state.get("on_no") == "select_step", (
            "continue_work must route the remediation path (on_no) to select_step"
        )

    def test_continue_work_escape_hatch_routes_to_final_verify(self, raw_data: dict) -> None:
        state = raw_data["states"]["continue_work"]
        assert state.get("on_yes") == "final_verify", (
            "continue_work must escape to final_verify when WORK_COMPLETE is emitted"
        )
        assert state.get("evaluate", {}).get("type") == "output_contains", (
            "continue_work must gate on WORK_COMPLETE via an output_contains evaluator"
        )
        assert "WORK_COMPLETE" in state["action"], (
            "continue_work.action must define the WORK_COMPLETE escape-hatch instruction"
        )

    def test_continue_work_action_type_is_prompt(self, raw_data: dict) -> None:
        state = raw_data["states"]["continue_work"]
        assert state.get("action_type") == "prompt"


class TestChange5DoWorkCapture:
    """Change 5 (ENH-1732): do_work state captures output for check_done delta input."""

    def test_do_work_has_capture_work_result(self, raw_data: dict) -> None:
        do_work_state = raw_data["states"]["do_work"]
        assert do_work_state.get("capture") == "work_result", (
            "do_work state must have capture: work_result so check_done can read the delta"
        )

    def test_do_work_prompts_for_last_files_output(self, raw_data: dict) -> None:
        action = raw_data["states"]["do_work"]["action"]
        assert "LAST_FILES" in action, (
            "do_work.action must instruct the model to write LAST_FILES to a temp file"
        )

    def test_do_work_must_not_modify_plan_file(self, raw_data: dict) -> None:
        action = raw_data["states"]["do_work"]["action"]
        assert "plan.md" in action, (
            "do_work.action must explicitly tell the model NOT to modify the plan file"
        )
        assert "Do NOT modify" in action or "do not modify" in action.lower(), (
            "do_work.action must explicitly prohibit modifying the plan file"
        )


class TestChange6CheckDoneDeltaAware:
    """Change 6 (ENH-1671): check_done.action scopes verification to the most recent step."""

    def test_check_done_references_captured_work_result(self, raw_data: dict) -> None:
        action = raw_data["states"]["check_done"]["action"]
        assert "captured.work_result.output" in action, (
            "check_done.action must reference captured.work_result.output for LAST_FILES delta context"
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


class TestENH1732StateSplit:
    """ENH-1732: execute split into select_step → do_work → verify_step → mark_done chain."""

    def test_plan_routes_to_resume_check(self, raw_data: dict) -> None:
        assert raw_data["states"]["plan"]["next"] == "resume_check"

    def test_resume_check_routes_no_to_select_step(self, raw_data: dict) -> None:
        assert raw_data["states"]["resume_check"]["on_no"] == "select_step"

    def test_resume_check_routes_yes_to_mark_done(self, raw_data: dict) -> None:
        assert raw_data["states"]["resume_check"]["on_yes"] == "mark_done"

    def test_resume_check_routes_error_to_diagnose(self, raw_data: dict) -> None:
        assert raw_data["states"]["resume_check"]["on_error"] == "diagnose"

    def test_select_step_action_type_is_shell(self, raw_data: dict) -> None:
        assert raw_data["states"]["select_step"]["action_type"] == "shell"

    def test_do_work_action_type_is_prompt(self, raw_data: dict) -> None:
        assert raw_data["states"]["do_work"]["action_type"] == "prompt"

    def test_verify_step_action_type_is_shell(self, raw_data: dict) -> None:
        assert raw_data["states"]["verify_step"]["action_type"] == "shell"

    def test_mark_done_action_type_is_shell(self, raw_data: dict) -> None:
        assert raw_data["states"]["mark_done"]["action_type"] == "shell"

    def test_select_step_routes_yes_to_do_work(self, raw_data: dict) -> None:
        assert raw_data["states"]["select_step"]["on_yes"] == "do_work"

    def test_select_step_routes_no_to_check_done(self, raw_data: dict) -> None:
        assert raw_data["states"]["select_step"]["on_no"] == "check_done"

    def test_select_step_routes_error_to_diagnose(self, raw_data: dict) -> None:
        assert raw_data["states"]["select_step"]["on_error"] == "diagnose"

    def test_do_work_routes_to_verify_step(self, raw_data: dict) -> None:
        assert raw_data["states"]["do_work"]["next"] == "verify_step"

    def test_do_work_retries_on_error(self, raw_data: dict) -> None:
        assert raw_data["states"]["do_work"]["on_error"] == "do_work"
        assert raw_data["states"]["do_work"]["max_retries"] == 2
        assert raw_data["states"]["do_work"]["on_retry_exhausted"] == "capture_work_exit"

    def test_continue_work_retries_on_error(self, raw_data: dict) -> None:
        assert raw_data["states"]["continue_work"]["on_error"] == "continue_work"
        assert raw_data["states"]["continue_work"]["max_retries"] == 3
        assert raw_data["states"]["continue_work"]["on_retry_exhausted"] == "diagnose"

    def test_do_work_timeout(self, raw_data: dict) -> None:
        timeout = raw_data["states"]["do_work"].get("timeout", 0)
        assert timeout > 0, "do_work must have an explicit timeout to bound per-step cost"
        assert timeout <= 900, "do_work timeout should be ≤900s (15 min) to prevent SIGKILL"

    def test_verify_step_routes_yes_to_mark_done(self, raw_data: dict) -> None:
        assert raw_data["states"]["verify_step"]["on_yes"] == "mark_done"

    def test_verify_step_routes_no_to_continue_work(self, raw_data: dict) -> None:
        assert raw_data["states"]["verify_step"]["on_no"] == "continue_work"

    def test_verify_step_routes_error_to_diagnose(self, raw_data: dict) -> None:
        assert raw_data["states"]["verify_step"]["on_error"] == "diagnose"

    def test_verify_step_evaluate_is_output_contains(self, raw_data: dict) -> None:
        evaluate = raw_data["states"]["verify_step"]["evaluate"]
        assert evaluate["type"] == "output_contains"
        assert evaluate["pattern"] == "VERIFY_PASS"

    def test_mark_done_routes_to_check_done(self, raw_data: dict) -> None:
        assert raw_data["states"]["mark_done"]["next"] == "check_done"

    def test_mark_done_routes_error_to_diagnose(self, raw_data: dict) -> None:
        assert raw_data["states"]["mark_done"]["on_error"] == "diagnose"

    def test_select_step_evaluate_is_output_contains(self, raw_data: dict) -> None:
        evaluate = raw_data["states"]["select_step"]["evaluate"]
        assert evaluate["type"] == "output_contains"
        assert evaluate["pattern"] == "SELECTED_STEP:"

    def test_execute_state_removed(self, raw_data: dict) -> None:
        assert "execute" not in raw_data.get("states", {}), (
            "execute state must be removed after ENH-1732 split"
        )

    def test_max_steps_increased(self, raw_data: dict) -> None:
        assert raw_data.get("max_steps", 0) >= 200, (
            "max_steps must be ≥200 to support ~33 plan steps at 6 iterations/step"
        )


# ---------------------------------------------------------------------------
# Shell action unit tests for ENH-1732 new states
# ---------------------------------------------------------------------------


def _load_state_script(state_name: str) -> str:
    """Extract the shell action from a named state."""
    with open(LOOP_FILE) as f:
        data = yaml.safe_load(f)
    return data["states"][state_name]["action"]


def _setup_run_dir(tmp_path: Path) -> Path:
    """Create a per-test run_dir (simulating ${context.run_dir})."""
    run_dir = tmp_path / "run_dir"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def _setup_loops_tmp(tmp_path: Path) -> Path:
    """DEPRECATED: use _setup_run_dir instead. Kept for backward compat during migration."""
    return _setup_run_dir(tmp_path)


class TestSelectStepShellAction:
    """Shell execution tests for the select_step action (ENH-1732)."""

    def _run(self, tmp_path: Path) -> subprocess.CompletedProcess[str]:
        run_dir = _setup_run_dir(tmp_path)
        script = _load_state_script("select_step")
        script = script.replace("${context.run_dir}", str(run_dir))
        script = script.replace("${context.input_hash}", "abc123def456")
        return _bash(script, cwd=tmp_path)

    def test_empty_plan_emits_no_unchecked_steps(self, tmp_path: Path) -> None:
        run_dir = _setup_run_dir(tmp_path)
        (run_dir / "plan.md").write_text("# Task Plan\n- [x] Step 1: done\n")
        result = self._run(tmp_path)
        assert result.returncode == 0, f"Script failed: {result.stderr}"
        assert "NO_UNCHECKED_STEPS" in result.stdout

    def test_unchecked_step_emits_selected_step(self, tmp_path: Path) -> None:
        run_dir = _setup_run_dir(tmp_path)
        (run_dir / "plan.md").write_text("# Task Plan\n- [x] Step 1: done\n- [ ] Step 2: pending\n")
        result = self._run(tmp_path)
        assert result.returncode == 0, f"Script failed: {result.stderr}"
        assert "SELECTED_STEP:" in result.stdout
        assert "Step 2: pending" in result.stdout

    def test_unchecked_step_writes_temp_file(self, tmp_path: Path) -> None:
        run_dir = _setup_run_dir(tmp_path)
        (run_dir / "plan.md").write_text("# Task Plan\n- [ ] Step 1: write code\n")
        self._run(tmp_path)
        step_file = run_dir / "current-step.txt"
        assert step_file.exists(), "select_step must write the step to current-step.txt"
        assert "Step 1: write code" in step_file.read_text()


class TestVerifyStepShellAction:
    """Shell execution tests for the verify_step per-step smoke gate.

    ENH-2225: verify_step is a language-agnostic per-step smoke gate that confirms
    the step's claimed files exist — it no longer runs the whole-suite test command
    (that moved to run_final_tests). These tests exercise the real smoke-gate
    contract, not a trivial always-pass.
    """

    def _run(self, tmp_path: Path) -> subprocess.CompletedProcess[str]:
        run_dir = _setup_run_dir(tmp_path)
        script = _load_state_script("verify_step")
        script = script.replace("${context.run_dir}", str(run_dir))
        return _bash(script, cwd=tmp_path)

    def test_missing_last_files_emits_verify_pass(self, tmp_path: Path) -> None:
        _setup_run_dir(tmp_path)
        # No last-files.txt written → nothing claimed → smoke gate passes.
        result = self._run(tmp_path)
        assert result.returncode == 0, f"Script failed: {result.stderr}"
        assert "VERIFY_PASS" in result.stdout

    def test_empty_files_list_emits_verify_pass(self, tmp_path: Path) -> None:
        run_dir = _setup_run_dir(tmp_path)
        (run_dir / "last-files.txt").write_text("LAST_FILES: \n")
        result = self._run(tmp_path)
        assert result.returncode == 0, f"Script failed: {result.stderr}"
        assert "VERIFY_PASS" in result.stdout

    def test_non_python_files_that_exist_emit_verify_pass(self, tmp_path: Path) -> None:
        # Language-agnostic (cf. BUG-2127): non-Python files that exist on disk pass.
        run_dir = _setup_run_dir(tmp_path)
        (tmp_path / "README.md").write_text("# readme\n")
        (tmp_path / "some-loop.yaml").write_text("name: x\n")
        (run_dir / "last-files.txt").write_text("LAST_FILES: README.md some-loop.yaml\n")
        result = self._run(tmp_path)
        assert result.returncode == 0, f"Script failed: {result.stderr}"
        assert "VERIFY_PASS" in result.stdout

    def test_missing_claimed_file_emits_verify_fail(self, tmp_path: Path) -> None:
        # A step that reports a file it did not actually produce fails the smoke gate.
        run_dir = _setup_run_dir(tmp_path)
        (tmp_path / "README.md").write_text("# readme\n")
        (run_dir / "last-files.txt").write_text("LAST_FILES: README.md does-not-exist.py\n")
        result = self._run(tmp_path)
        assert "VERIFY_PASS" not in result.stdout
        assert "VERIFY_FAIL" in result.stdout

    def test_verify_step_does_not_resolve_test_cmd(self) -> None:
        # ENH-2225: per-step gate must NOT run the whole-suite command. Assert on the
        # functional resolution/execution markers (not prose, which may reference the
        # behavior in comments).
        script = _load_state_script("verify_step")
        assert "cfg.get('project'" not in script, (
            "verify_step must not read project.test_cmd from config"
        )
        assert 'eval "$CMD"' not in script, "verify_step must not execute a resolved test command"


class TestMarkDoneShellAction:
    """Shell execution tests for the mark_done action (ENH-1732)."""

    def _run(self, tmp_path: Path) -> subprocess.CompletedProcess[str]:
        run_dir = _setup_run_dir(tmp_path)
        script = _load_state_script("mark_done")
        script = script.replace("${context.run_dir}", str(run_dir))
        return _bash(script, cwd=tmp_path)

    def test_marks_selected_step_as_done(self, tmp_path: Path) -> None:
        run_dir = _setup_run_dir(tmp_path)
        (run_dir / "plan.md").write_text(
            "# Task Plan\n- [x] Step 1: done\n- [ ] Step 2: pending\n- [ ] Step 3: also pending\n"
        )
        (run_dir / "current-step.txt").write_text("- [ ] Step 2: pending\n")
        result = self._run(tmp_path)
        assert result.returncode == 0, f"Script failed: {result.stderr}"
        plan = (run_dir / "plan.md").read_text()
        lines = plan.splitlines()
        assert "- [x] Step 1: done" in lines
        assert "- [x] Step 2: pending" in lines
        assert "- [ ] Step 3: also pending" in lines

    def test_removes_current_step_temp_file(self, tmp_path: Path) -> None:
        run_dir = _setup_run_dir(tmp_path)
        (run_dir / "plan.md").write_text("# Task Plan\n- [ ] Step 1: write code\n")
        step_file = run_dir / "current-step.txt"
        step_file.write_text("- [ ] Step 1: write code\n")
        self._run(tmp_path)
        assert not step_file.exists(), "mark_done must remove current-step.txt"

    def test_marks_only_the_selected_step(self, tmp_path: Path) -> None:
        run_dir = _setup_run_dir(tmp_path)
        (run_dir / "plan.md").write_text("# Task Plan\n- [ ] Step 1: first\n- [ ] Step 2: second\n")
        (run_dir / "current-step.txt").write_text("- [ ] Step 1: first\n")
        self._run(tmp_path)
        plan = (run_dir / "plan.md").read_text()
        assert "- [x] Step 1: first" in plan
        assert "- [ ] Step 2: second" in plan


class TestCheckpointWriteShellAction:
    """ENH-1735: select_step writes in-flight checkpoint before routing to do_work."""

    def _run(self, tmp_path: Path) -> subprocess.CompletedProcess[str]:
        run_dir = _setup_run_dir(tmp_path)
        script = _load_state_script("select_step")
        script = script.replace("${context.run_dir}", str(run_dir))
        script = script.replace("${context.input_hash}", "abc123def456")
        return _bash(script, cwd=tmp_path)

    def test_checkpoint_written_when_step_found(self, tmp_path: Path) -> None:
        run_dir = _setup_run_dir(tmp_path)
        (run_dir / "plan.md").write_text("# Task Plan\n- [ ] Step 1: write code\n")
        self._run(tmp_path)
        checkpoint = run_dir / "checkpoint.json"
        assert checkpoint.exists(), "select_step must write checkpoint.json"

    def test_checkpoint_contains_step_text(self, tmp_path: Path) -> None:
        import json

        run_dir = _setup_run_dir(tmp_path)
        (run_dir / "plan.md").write_text("# Task Plan\n- [ ] Step 1: write code\n")
        self._run(tmp_path)
        checkpoint = run_dir / "checkpoint.json"
        data = json.loads(checkpoint.read_text())
        assert "in_flight_step" in data
        assert "Step 1: write code" in data["in_flight_step"]

    def test_checkpoint_not_written_when_no_steps(self, tmp_path: Path) -> None:
        run_dir = _setup_run_dir(tmp_path)
        (run_dir / "plan.md").write_text("# Task Plan\n- [x] Step 1: done\n")
        self._run(tmp_path)
        checkpoint = run_dir / "checkpoint.json"
        assert not checkpoint.exists(), (
            "select_step must not write checkpoint when no unchecked steps remain"
        )


class TestCheckpointClearShellAction:
    """ENH-1735: mark_done clears the in-flight checkpoint after step completion."""

    def _run(self, tmp_path: Path) -> subprocess.CompletedProcess[str]:
        run_dir = _setup_run_dir(tmp_path)
        script = _load_state_script("mark_done")
        script = script.replace("${context.run_dir}", str(run_dir))
        return _bash(script, cwd=tmp_path)

    def test_removes_checkpoint_when_present(self, tmp_path: Path) -> None:
        run_dir = _setup_run_dir(tmp_path)
        (run_dir / "plan.md").write_text("# Task Plan\n- [ ] Step 1: write code\n")
        step_file = run_dir / "current-step.txt"
        step_file.write_text("- [ ] Step 1: write code\n")
        checkpoint = run_dir / "checkpoint.json"
        checkpoint.write_text(
            '{"in_flight_step":"- [ ] Step 1: write code","timestamp":"2026-01-01T00:00:00Z"}'
        )
        self._run(tmp_path)
        assert not checkpoint.exists(), "mark_done must remove checkpoint.json"

    def test_tolerates_missing_checkpoint(self, tmp_path: Path) -> None:
        run_dir = _setup_run_dir(tmp_path)
        (run_dir / "plan.md").write_text("# Task Plan\n- [ ] Step 1: write code\n")
        step_file = run_dir / "current-step.txt"
        step_file.write_text("- [ ] Step 1: write code\n")
        result = self._run(tmp_path)
        assert result.returncode == 0, "mark_done must not fail when checkpoint is absent"


class TestResumeCheckShellAction:
    """ENH-1735: resume_check detects in-flight checkpoint and routes to mark_done or select_step."""

    def _run(self, tmp_path: Path) -> subprocess.CompletedProcess[str]:
        run_dir = _setup_run_dir(tmp_path)
        script = _load_state_script("resume_check")
        script = script.replace("${context.run_dir}", str(run_dir))
        script = script.replace("${context.input_hash}", "abc123def456")
        return _bash(script, cwd=tmp_path)

    def test_no_checkpoint_emits_resume_none(self, tmp_path: Path) -> None:
        _setup_run_dir(tmp_path)
        result = self._run(tmp_path)
        assert result.returncode == 0, f"Script failed: {result.stderr}"
        assert "RESUME_NONE" in result.stdout

    def test_checkpoint_with_existing_files_emits_resume_skip(self, tmp_path: Path) -> None:
        run_dir = _setup_run_dir(tmp_path)
        checkpoint = run_dir / "checkpoint.json"
        checkpoint.write_text(
            '{"in_flight_step":"- [ ] Step 1: write code","timestamp":"2026-01-01T00:00:00Z","task_hash":"abc123def456"}'
        )
        (run_dir / "current-step.txt").write_text("- [ ] Step 1: write code\n")
        output_file = tmp_path / "output.py"
        output_file.write_text("# output\n")
        (run_dir / "last-files.txt").write_text(f"LAST_FILES: {output_file}\n")
        result = self._run(tmp_path)
        assert result.returncode == 0, f"Script failed: {result.stderr}"
        assert "RESUME_SKIP" in result.stdout

    def test_checkpoint_with_missing_files_emits_resume_clean(self, tmp_path: Path) -> None:
        run_dir = _setup_run_dir(tmp_path)
        checkpoint = run_dir / "checkpoint.json"
        checkpoint.write_text(
            '{"in_flight_step":"- [ ] Step 1: write code","timestamp":"2026-01-01T00:00:00Z","task_hash":"abc123def456"}'
        )
        (run_dir / "current-step.txt").write_text("- [ ] Step 1: write code\n")
        (run_dir / "last-files.txt").write_text("LAST_FILES: /nonexistent/file.py\n")
        result = self._run(tmp_path)
        assert result.returncode == 0, f"Script failed: {result.stderr}"
        assert "RESUME_CLEAN" in result.stdout
        assert not checkpoint.exists(), "resume_check must delete checkpoint on RESUME_CLEAN"

    def test_checkpoint_without_last_files_emits_resume_clean(self, tmp_path: Path) -> None:
        run_dir = _setup_run_dir(tmp_path)
        checkpoint = run_dir / "checkpoint.json"
        checkpoint.write_text(
            '{"in_flight_step":"- [ ] Step 1: write code","timestamp":"2026-01-01T00:00:00Z","task_hash":"abc123def456"}'
        )
        (run_dir / "current-step.txt").write_text("- [ ] Step 1: write code\n")
        result = self._run(tmp_path)
        assert result.returncode == 0, f"Script failed: {result.stderr}"
        assert "RESUME_CLEAN" in result.stdout
        assert not checkpoint.exists(), "resume_check must delete checkpoint when no last-files.txt"


class TestBUG1766ConvergenceEfficiency:
    """BUG-1766: stop the general-task loop from re-executing finished work.

    Four coordinated edits to general-task.yaml:
    1. mark_done marks the line selected by select_step (current-step.txt), not the
       first unchecked line, so marking can never desync from selection.
    2. continue_work refuses to append near-duplicate remediation steps.
    3. define_done forbids DoD criteria that target the loop's own tracking files.
    4. continue_work no longer asserts the false "plan is fully [x]" premise.
    """

    def _run_mark_done(self, tmp_path: Path) -> subprocess.CompletedProcess[str]:
        run_dir = _setup_run_dir(tmp_path)
        script = _load_state_script("mark_done")
        script = script.replace("${context.run_dir}", str(run_dir))
        return _bash(script, cwd=tmp_path)

    # --- Edit 1: mark_done bound to the selected step ----------------------

    def test_mark_done_marks_selected_step_not_first_unchecked(self, tmp_path: Path) -> None:
        """current-step.txt points at a LATER step; mark_done must mark THAT one."""
        run_dir = _setup_run_dir(tmp_path)
        (run_dir / "plan.md").write_text(
            "# Task Plan\n- [x] Step 1: done\n- [ ] Step 2: second\n- [ ] Step 3: third\n"
        )
        (run_dir / "current-step.txt").write_text("- [ ] Step 3: third\n")
        result = self._run_mark_done(tmp_path)
        assert result.returncode == 0, f"Script failed: {result.stderr}"
        plan = (run_dir / "plan.md").read_text()
        assert "- [x] Step 3: third" in plan, "mark_done must mark the SELECTED step"
        assert "- [ ] Step 2: second" in plan, (
            "mark_done must NOT mark the first unchecked step when a later step is selected"
        )

    def test_mark_done_falls_back_to_first_unchecked_when_no_current_step(
        self, tmp_path: Path
    ) -> None:
        """With no current-step.txt, mark_done safely marks the first unchecked step."""
        run_dir = _setup_run_dir(tmp_path)
        (run_dir / "plan.md").write_text("# Task Plan\n- [ ] Step 1: first\n- [ ] Step 2: second\n")
        result = self._run_mark_done(tmp_path)
        assert result.returncode == 0, f"Script failed: {result.stderr}"
        plan = (run_dir / "plan.md").read_text()
        assert "- [x] Step 1: first" in plan
        assert "- [ ] Step 2: second" in plan

    def test_mark_done_action_references_current_step_file(self, raw_data: dict) -> None:
        action = raw_data["states"]["mark_done"]["action"]
        assert "current-step.txt" in action
        assert "STEP_TEXT" in action and "target" in action, (
            "mark_done must bind marking to current-step.txt content"
        )

    # --- Edit 2: continue_work dedup guard ---------------------------------

    def test_continue_work_has_dedup_guard(self, raw_data: dict) -> None:
        action = raw_data["states"]["continue_work"]["action"]
        assert "near-duplicate" in action, "continue_work must contain a dedup guard"
        assert "do NOT append another one" in action

    # --- Edit 3: define_done forbids tracking-file criteria ----------------

    def test_define_done_forbids_tracking_file_criteria(self, raw_data: dict) -> None:
        action = raw_data["states"]["define_done"]["action"]
        assert "Do NOT write DoD criteria that target" in action
        assert "plan.md" in action and "dod.md" in action

    # --- Edit 4: continue_work false-premise prompt fixed ------------------

    def test_continue_work_drops_false_plan_complete_premise(self, raw_data: dict) -> None:
        action = raw_data["states"]["continue_work"]["action"]
        assert (
            "The plan is fully [x] but at least one DoD criterion remains unchecked" not in action
        )
        assert "checked vs unchecked" in action


# ---------------------------------------------------------------------------
# Helpers for shell execution tests (modeled on test_loops_recursive_refine.py)
# ---------------------------------------------------------------------------


def _bash(script: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", "-c", script], cwd=cwd, capture_output=True, text=True)


def _load_count_done_script(
    context_overrides: dict | None = None,
    run_dir: Path | None = None,
) -> str:
    """Extract the shell action from count_done, with context variables interpolated."""
    with open(LOOP_FILE) as f:
        data = yaml.safe_load(f)
    script = data["states"]["count_done"]["action"]
    ctx = {**data.get("context", {}), **(context_overrides or {})}
    for key, val in ctx.items():
        script = script.replace(f"${{context.{key}}}", str(val))
    if run_dir is not None:
        script = script.replace("${context.run_dir}", str(run_dir))
    return script


def _setup_dod_plan(
    tmp_path: Path,
    *,
    dod_content: str,
    plan_content: str,
) -> Path:
    """Set up DoD and plan files in a run_dir. Returns the run_dir Path."""
    run_dir = _setup_run_dir(tmp_path)
    (run_dir / "dod.md").write_text(dod_content)
    (run_dir / "plan.md").write_text(plan_content)
    return run_dir


_ALL_DONE_DOD = """\
# Definition of Done
## Verification Criteria
- [x] Tests pass
- [x] File exists
## Sample Verification
- [x] Tests pass: ran pytest, all green
"""

_ALL_DONE_PLAN = """\
# Task Plan
- [x] Step 1: write code
- [x] Step 2: run tests
"""

_UNCHECKED_DOD = """\
# Definition of Done
## Verification Criteria
- [x] Tests pass
- [ ] File exists
"""

_UNCHECKED_PLAN = """\
# Task Plan
- [x] Step 1: write code
- [ ] Step 2: run tests
"""

# Fixture with one hard criterion unchecked — hard criteria always block.
_HARD_UNCHECKED_DOD = """\
# Definition of Done
## Verification Criteria
- [ ] Tests pass [hard]
- [x] File exists
## Sample Verification
- [x] File exists: file found at expected path
"""

# Fixture for scenario: all hard done, 1 soft unchecked, pass rate == 95% (19/20).
# This verifies that soft criteria are non-blocking when pass rate meets threshold.
_SOFT_UNCHECKED_PASS_RATE_OK_DOD = """\
# Definition of Done
## Verification Criteria
- [x] Tests pass [hard]
- [x] File exists
- [x] Build succeeds
- [x] Lint passes
- [x] Type checks pass
- [x] Docs updated
- [x] Coverage meets target
- [x] API unchanged
- [x] PR reviewed
- [x] Deploy tested
- [x] Integration tests pass
- [x] Security scan clear
- [x] Performance baseline met
- [x] Stakeholder notified
- [x] Release notes drafted
- [x] Changelog updated
- [x] Version bumped
- [x] CI pipeline green
- [x] Environment verified
- [ ] Working tree is clean
## Sample Verification
- [x] Tests pass: ran pytest, all green
"""


class TestCountDoneShellScript:
    """Shell execution tests for the count_done action (ENH-1658)."""

    def test_all_done_emits_total_zero(self, tmp_path: Path) -> None:
        run_dir = _setup_dod_plan(tmp_path, dod_content=_ALL_DONE_DOD, plan_content=_ALL_DONE_PLAN)
        script = _load_count_done_script(run_dir=run_dir)
        result = _bash(script, cwd=tmp_path)
        assert result.returncode == 0, f"Script failed: {result.stderr}"
        import json

        data = json.loads(result.stdout.strip())
        assert data["total"] == 0
        assert data["hard_unchecked_dod"] == 0
        assert data["soft_unchecked_dod"] == 0
        assert data["unchecked_plan"] == 0
        assert data["failed_samples"] == 0

    def test_unchecked_criterion_emits_nonzero_total(self, tmp_path: Path) -> None:
        run_dir = _setup_dod_plan(
            tmp_path, dod_content=_UNCHECKED_DOD, plan_content=_UNCHECKED_PLAN
        )
        script = _load_count_done_script(run_dir=run_dir)
        result = _bash(script, cwd=tmp_path)
        assert result.returncode == 0, f"Script failed: {result.stderr}"
        import json

        data = json.loads(result.stdout.strip())
        assert data["total"] > 0
        assert data["hard_unchecked_dod"] == 0  # no [hard] tags in fixture
        assert data["soft_unchecked_dod"] >= 1  # unchecked criterion is soft (no [hard] tag)
        assert data["unchecked_plan"] >= 1

    def test_missing_dod_exits_nonzero(self, tmp_path: Path) -> None:
        run_dir = _setup_run_dir(tmp_path)
        # Only create plan, not DoD
        (run_dir / "plan.md").write_text(_ALL_DONE_PLAN)
        script = _load_count_done_script(run_dir=run_dir)
        result = _bash(script, cwd=tmp_path)
        assert result.returncode != 0, "Script must exit non-zero when DoD file is missing"

    def test_failed_sample_reported_but_does_not_gate_total(self, tmp_path: Path) -> None:
        # A FAILED sample is reported for observability but no longer drives `total`:
        # Sample Verification prose accumulates and re-emits historical FAILEDs, which
        # permanently poisoned the gate. Genuine failures block authoritatively via the
        # criterion being flipped back to [ ] (see next test), not via failed_samples.
        dod_with_failed = """\
# Definition of Done
## Verification Criteria
- [x] Tests pass
## Sample Verification
- [ ] Tests pass: FAILED — pytest returned exit 1
"""
        run_dir = _setup_dod_plan(
            tmp_path, dod_content=dod_with_failed, plan_content=_ALL_DONE_PLAN
        )
        script = _load_count_done_script(run_dir=run_dir)
        result = _bash(script, cwd=tmp_path)
        assert result.returncode == 0, f"Script failed: {result.stderr}"
        import json

        data = json.loads(result.stdout.strip())
        assert data["failed_samples"] >= 1, "failed_samples must still be reported"
        assert data["total"] == 0, (
            "a FAILED sample alone must NOT gate completion — the criterion is still [x] "
            "and the plan is complete, so total is 0"
        )

    def test_flipped_back_criterion_gates_total(self, tmp_path: Path) -> None:
        # The authoritative block for a genuine sample failure: check_done flips the
        # criterion back to [ ], which HARD/SOFT_UNCHECKED_DOD counts into total.
        dod_flipped_back = """\
# Definition of Done
## Verification Criteria
- [ ] Tests pass [hard]
## Sample Verification
- [ ] Tests pass: FAILED — pytest returned exit 1
"""
        run_dir = _setup_dod_plan(
            tmp_path, dod_content=dod_flipped_back, plan_content=_ALL_DONE_PLAN
        )
        script = _load_count_done_script(run_dir=run_dir)
        result = _bash(script, cwd=tmp_path)
        assert result.returncode == 0, f"Script failed: {result.stderr}"
        import json

        data = json.loads(result.stdout.strip())
        assert data["hard_unchecked_dod"] >= 1
        assert data["total"] >= 1, "a flipped-back unchecked hard criterion must block"


class TestENH1676PartialDoDThreshold:
    """ENH-1676: two-tier hard/soft DoD threshold in count_done shell script."""

    def test_context_has_min_pass_rate_and_hard_criteria_tags(self) -> None:
        with open(LOOP_FILE) as f:
            raw_data = yaml.safe_load(f)
        ctx = raw_data.get("context", {})
        assert "min_pass_rate" in ctx, "context must define min_pass_rate"
        assert "hard_criteria_tags" in ctx, "context must define hard_criteria_tags"

    def test_hard_criteria_unchecked_blocks_when_plan_done(self, tmp_path: Path) -> None:
        run_dir = _setup_dod_plan(
            tmp_path, dod_content=_HARD_UNCHECKED_DOD, plan_content=_ALL_DONE_PLAN
        )
        script = _load_count_done_script(run_dir=run_dir)
        result = _bash(script, cwd=tmp_path)
        assert result.returncode == 0, f"Script failed: {result.stderr}"
        import json

        data = json.loads(result.stdout.strip())
        assert data["hard_unchecked_dod"] >= 1
        assert data["total"] > 0, "unmet hard criterion must block routing to done"

    def test_all_hard_done_routes_done(self, tmp_path: Path) -> None:
        run_dir = _setup_dod_plan(tmp_path, dod_content=_ALL_DONE_DOD, plan_content=_ALL_DONE_PLAN)
        script = _load_count_done_script(run_dir=run_dir)
        result = _bash(script, cwd=tmp_path)
        assert result.returncode == 0, f"Script failed: {result.stderr}"
        import json

        data = json.loads(result.stdout.strip())
        assert data["hard_unchecked_dod"] == 0
        assert data["total"] == 0, "all criteria checked → total must be 0"

    def test_all_hard_done_with_soft_unchecked_routes_done_when_pass_rate_met(
        self, tmp_path: Path
    ) -> None:
        # 19 of 20 criteria checked → 95% pass rate == min_pass_rate; soft criterion is non-blocking.
        run_dir = _setup_dod_plan(
            tmp_path,
            dod_content=_SOFT_UNCHECKED_PASS_RATE_OK_DOD,
            plan_content=_ALL_DONE_PLAN,
        )
        script = _load_count_done_script(run_dir=run_dir)
        result = _bash(script, cwd=tmp_path)
        assert result.returncode == 0, f"Script failed: {result.stderr}"
        import json

        data = json.loads(result.stdout.strip())
        assert data["hard_unchecked_dod"] == 0
        assert data["soft_unchecked_dod"] >= 1
        assert data["total"] == 0, "soft criterion is non-blocking when pass rate meets threshold"


# ---------------------------------------------------------------------------
# ENH-1681: final_verify + count_final terminal gate
# ---------------------------------------------------------------------------


def _load_count_final_script(run_dir: Path | None = None) -> str:
    """Extract the shell action from count_final."""
    with open(LOOP_FILE) as f:
        data = yaml.safe_load(f)
    script = data["states"]["count_final"]["action"]
    if run_dir is not None:
        script = script.replace("${context.run_dir}", str(run_dir))
    return script


class TestChange8FinalVerifyGate:
    """Change 8 (ENH-1681): final_verify + count_final terminal gate between count_done and done."""

    def test_count_done_routes_yes_to_final_verify(self, raw_data: dict) -> None:
        assert raw_data["states"]["count_done"]["on_yes"] == "final_verify"

    def test_final_verify_action_type_is_prompt(self, raw_data: dict) -> None:
        assert raw_data["states"]["final_verify"]["action_type"] == "prompt"

    def test_final_verify_routes_next_to_run_final_tests(self, raw_data: dict) -> None:
        # ENH-2225: run_final_tests (the final-only whole-suite gate) is inserted
        # between final_verify and count_final.
        assert raw_data["states"]["final_verify"]["next"] == "run_final_tests"

    def test_final_verify_routes_error_to_diagnose(self, raw_data: dict) -> None:
        assert raw_data["states"]["final_verify"]["on_error"] == "diagnose"

    def test_final_verify_action_references_dod_file(self, raw_data: dict) -> None:
        action = raw_data["states"]["final_verify"]["action"]
        assert "dod.md" in action

    def test_final_verify_action_has_final_verification_section(self, raw_data: dict) -> None:
        action = raw_data["states"]["final_verify"]["action"]
        assert "## Final Verification" in action

    def test_count_final_action_type_is_shell(self, raw_data: dict) -> None:
        assert raw_data["states"]["count_final"]["action_type"] == "shell"

    def test_count_final_evaluate_type_is_output_json(self, raw_data: dict) -> None:
        evaluate = raw_data["states"]["count_final"]["evaluate"]
        assert evaluate["type"] == "output_json"

    def test_count_final_evaluate_path_is_failed_finals(self, raw_data: dict) -> None:
        evaluate = raw_data["states"]["count_final"]["evaluate"]
        assert evaluate["path"] == ".failed_finals"

    def test_count_final_evaluate_operator_eq_zero(self, raw_data: dict) -> None:
        evaluate = raw_data["states"]["count_final"]["evaluate"]
        assert evaluate["operator"] == "eq"
        assert evaluate["target"] == 0

    def test_count_final_routes_yes_to_done(self, raw_data: dict) -> None:
        assert raw_data["states"]["count_final"]["on_yes"] == "done"

    def test_count_final_routes_no_to_continue_work(self, raw_data: dict) -> None:
        assert raw_data["states"]["count_final"]["on_no"] == "continue_work"

    def test_count_final_routes_error_to_diagnose(self, raw_data: dict) -> None:
        assert raw_data["states"]["count_final"]["on_error"] == "diagnose"

    def test_count_final_captures_final_counts(self, raw_data: dict) -> None:
        assert raw_data["states"]["count_final"]["capture"] == "final_counts"


_CLEAN_FINAL_DOD = """\
# Definition of Done
## Verification Criteria
- [x] Tests pass
- [x] File exists
## Final Verification
- [x] Tests pass: ran pytest, all green
- [x] File exists: confirmed at expected path
"""

_ONE_FAILED_FINAL_DOD = """\
# Definition of Done
## Verification Criteria
- [x] Tests pass
- [ ] File exists (final_verify: failed — file was deleted)
## Final Verification
- [x] Tests pass: ran pytest, all green
- [ ] File exists: FAILED — file not found at expected path
"""

_TWO_SECTIONS_FINAL_DOD = """\
# Definition of Done
## Verification Criteria
- [x] Tests pass
- [x] File exists
## Final Verification
- [x] Tests pass: ran pytest, all green
- [ ] File exists: FAILED — old failure from prior pass
## Final Verification
- [x] Tests pass: ran pytest, all green
- [x] File exists: confirmed at expected path
"""


class TestCountFinalShellScript:
    """Shell execution tests for the count_final action (ENH-1681)."""

    def test_clean_final_verification_emits_zero_failed(self, tmp_path: Path) -> None:
        run_dir = _setup_dod_plan(
            tmp_path, dod_content=_CLEAN_FINAL_DOD, plan_content=_ALL_DONE_PLAN
        )
        script = _load_count_final_script(run_dir=run_dir)
        result = _bash(script, cwd=tmp_path)
        assert result.returncode == 0, f"Script failed: {result.stderr}"
        import json

        data = json.loads(result.stdout.strip())
        assert data["failed_finals"] == 0

    def test_one_failed_entry_emits_nonzero(self, tmp_path: Path) -> None:
        run_dir = _setup_dod_plan(
            tmp_path, dod_content=_ONE_FAILED_FINAL_DOD, plan_content=_ALL_DONE_PLAN
        )
        script = _load_count_final_script(run_dir=run_dir)
        result = _bash(script, cwd=tmp_path)
        assert result.returncode == 0, f"Script failed: {result.stderr}"
        import json

        data = json.loads(result.stdout.strip())
        assert data["failed_finals"] == 1

    def test_two_sections_only_counts_most_recent(self, tmp_path: Path) -> None:
        # Two accumulated ## Final Verification sections; only the last one is clean.
        run_dir = _setup_dod_plan(
            tmp_path, dod_content=_TWO_SECTIONS_FINAL_DOD, plan_content=_ALL_DONE_PLAN
        )
        script = _load_count_final_script(run_dir=run_dir)
        result = _bash(script, cwd=tmp_path)
        assert result.returncode == 0, f"Script failed: {result.stderr}"
        import json

        data = json.loads(result.stdout.strip())
        assert data["failed_finals"] == 0, (
            "awk count reset must ensure only the most-recent Final Verification section is tallied"
        )

    def test_missing_dod_exits_nonzero(self, tmp_path: Path) -> None:
        run_dir = _setup_run_dir(tmp_path)
        script = _load_count_final_script(run_dir=run_dir)
        result = _bash(script, cwd=tmp_path)
        assert result.returncode != 0, "Script must exit non-zero when DoD file is missing"


class TestENH2225FinalOnlyGate:
    """ENH-2225: whole-suite test command runs only at completion (run_final_tests),
    not per-step (verify_step). Whole-artifact gates (coverage thresholds) no longer
    block every individual step mid-implementation."""

    def test_import_includes_common_lib(self, raw_data: dict) -> None:
        assert "lib/common.yaml" in raw_data.get("import", [])

    def test_verify_step_does_not_resolve_test_cmd(self, raw_data: dict) -> None:
        # Per-step gate must not run the configured/whole-suite test command. Assert on
        # functional resolution/execution markers, not prose (comments may describe it).
        action = raw_data["states"]["verify_step"]["action"]
        assert "cfg.get('project'" not in action
        assert 'eval "$CMD"' not in action

    def test_verify_step_keeps_output_contains_evaluator(self, raw_data: dict) -> None:
        # Preserve the VERIFY_PASS / output_contains contract (BUG-1732).
        evaluate = raw_data["states"]["verify_step"]["evaluate"]
        assert evaluate["type"] == "output_contains"
        assert evaluate["pattern"] == "VERIFY_PASS"

    def test_run_final_tests_state_exists(self, raw_data: dict) -> None:
        assert "run_final_tests" in raw_data["states"]

    def test_run_final_tests_uses_shell_exit_fragment(self, raw_data: dict) -> None:
        state = raw_data["states"]["run_final_tests"]
        assert state.get("fragment") == "shell_exit"

    def test_run_final_tests_resolves_test_cmd(self, raw_data: dict) -> None:
        # The whole-suite gate IS the place the resolved test command runs.
        action = raw_data["states"]["run_final_tests"]["action"]
        assert "${context.test_cmd}" in action
        assert "ll-config.json" in action
        assert "pytest" in action

    def test_run_final_tests_routing(self, raw_data: dict) -> None:
        state = raw_data["states"]["run_final_tests"]
        assert state["on_yes"] == "count_final"
        assert state["on_no"] == "continue_work"
        assert state["on_error"] == "diagnose"

    def test_final_verify_routes_to_run_final_tests(self, raw_data: dict) -> None:
        assert raw_data["states"]["final_verify"]["next"] == "run_final_tests"


class TestRunFinalTestsShellAction:
    """Shell execution tests for run_final_tests — the final-only whole-suite gate
    (ENH-2225). Pattern mirrors TestCountFinalShellScript / TestVerifyStepShellAction."""

    def _load(self, run_dir: Path, test_cmd: str = "") -> str:
        with open(LOOP_FILE) as f:
            data = yaml.safe_load(f)
        script = data["states"]["run_final_tests"]["action"]
        script = script.replace("${context.test_cmd}", test_cmd)
        script = script.replace("${context.run_dir}", str(run_dir))
        return script

    def test_passing_command_exits_zero(self, tmp_path: Path) -> None:
        run_dir = _setup_run_dir(tmp_path)
        script = self._load(run_dir, test_cmd="true")
        result = _bash(script, cwd=tmp_path)
        assert result.returncode == 0, f"Script failed: {result.stderr}"
        # output is captured for continue_work to read.
        assert (run_dir / "verify-output.txt").exists()

    def test_failing_command_exits_nonzero(self, tmp_path: Path) -> None:
        run_dir = _setup_run_dir(tmp_path)
        # Simulate a whole-suite gate failing (e.g. coverage below threshold).
        script = self._load(run_dir, test_cmd="echo 'coverage too low' && false")
        result = _bash(script, cwd=tmp_path)
        assert result.returncode != 0, (
            "run_final_tests must propagate the test command's failure exit code"
        )
        assert "coverage too low" in (run_dir / "verify-output.txt").read_text()

    def test_falls_back_to_config_test_cmd(self, tmp_path: Path) -> None:
        # Empty test_cmd → read project.test_cmd from .ll/ll-config.json.
        run_dir = _setup_run_dir(tmp_path)
        (tmp_path / ".ll").mkdir()
        (tmp_path / ".ll" / "ll-config.json").write_text('{"project": {"test_cmd": "true"}}')
        script = self._load(run_dir, test_cmd="")
        result = _bash(script, cwd=tmp_path)
        assert result.returncode == 0, f"Script failed: {result.stderr}"


class TestENH1631SummarizePartial:
    """ENH-1631: on_max_iterations: summarize_partial wiring in general-task.yaml."""

    def test_on_max_steps_set_to_summarize_partial(self, raw_data: dict) -> None:
        assert raw_data.get("on_max_steps") == "summarize_partial"

    def test_summarize_partial_state_exists(self, raw_data: dict) -> None:
        assert "summarize_partial" in raw_data.get("states", {})

    def test_summarize_partial_action_references_dod_artifact(self, raw_data: dict) -> None:
        action = raw_data["states"]["summarize_partial"].get("action", "")
        assert "dod.md" in action

    def test_summarize_partial_action_references_plan_artifact(self, raw_data: dict) -> None:
        action = raw_data["states"]["summarize_partial"].get("action", "")
        assert "plan.md" in action

    def test_summarize_partial_action_references_summary_artifact(self, raw_data: dict) -> None:
        action = raw_data["states"]["summarize_partial"].get("action", "")
        assert "summary.md" in action

    def test_summarize_partial_routes_to_done(self, raw_data: dict) -> None:
        state = raw_data["states"]["summarize_partial"]
        assert state.get("next") == "done"


class TestBUG1724TimeoutProtection:
    """BUG-1724: All prompt-type states must be protected from the 3600s fallback."""

    def test_default_timeout_set(self, raw_data: dict) -> None:
        assert raw_data.get("default_timeout") == 1800, (
            "general-task.yaml must have default_timeout: 1800 to cap all states at 1800s "
            "instead of the 3600s hardcoded fallback in FSMExecutor._run_action()"
        )

    def test_final_verify_has_per_state_timeout(self, raw_data: dict) -> None:
        assert raw_data["states"]["final_verify"].get("timeout", 0) > 0, (
            "final_verify must have an explicit per-state timeout so it is not silently "
            "skipped when default_timeout is the only protection"
        )


# ---------------------------------------------------------------------------
# BUG-1960: cross-run state corruption fixes
# ---------------------------------------------------------------------------


class TestResumeCheckBUG1960:
    """BUG-1960: resume_check detects stale/corrupt state from prior runs."""

    def _run(self, tmp_path: Path) -> subprocess.CompletedProcess[str]:
        run_dir = _setup_run_dir(tmp_path)
        script = _load_state_script("resume_check")
        script = script.replace("${context.run_dir}", str(run_dir))
        script = script.replace("${context.input_hash}", "abc123def456")
        return _bash(script, cwd=tmp_path)

    def test_checkpoint_without_current_step_emits_resume_clean(self, tmp_path: Path) -> None:
        """Fix 2: checkpoint exists but current-step.txt is missing → RESUME_CLEAN."""
        run_dir = _setup_run_dir(tmp_path)
        checkpoint = run_dir / "checkpoint.json"
        checkpoint.write_text(
            '{"in_flight_step":"- [ ] Step 1: write code",'
            '"timestamp":"2026-01-01T00:00:00Z",'
            '"task_hash":"abc123def456"}'
        )
        # current-step.txt intentionally NOT created
        result = self._run(tmp_path)
        assert result.returncode == 0, f"Script failed: {result.stderr}"
        assert "RESUME_CLEAN" in result.stdout
        assert not checkpoint.exists(), (
            "resume_check must delete checkpoint when current-step.txt is missing"
        )

    def test_checkpoint_task_hash_mismatch_emits_resume_clean(self, tmp_path: Path) -> None:
        """Fix 3: checkpoint from a different task → RESUME_CLEAN."""
        run_dir = _setup_run_dir(tmp_path)
        checkpoint = run_dir / "checkpoint.json"
        checkpoint.write_text(
            '{"in_flight_step":"- [ ] Step 1: write code",'
            '"timestamp":"2026-01-01T00:00:00Z",'
            '"task_hash":"different_task_hash"}'
        )
        (run_dir / "current-step.txt").write_text("- [ ] Step 1: write code\n")
        result = self._run(tmp_path)
        assert result.returncode == 0, f"Script failed: {result.stderr}"
        assert "RESUME_CLEAN" in result.stdout
        assert not checkpoint.exists(), (
            "resume_check must discard checkpoint when task_hash doesn't match"
        )

    def test_checkpoint_no_hash_field_skips_hash_check(self, tmp_path: Path) -> None:
        """Backward compat: checkpoint without task_hash field skips the check."""
        run_dir = _setup_run_dir(tmp_path)
        checkpoint = run_dir / "checkpoint.json"
        checkpoint.write_text(
            '{"in_flight_step":"- [ ] Step 1: write code","timestamp":"2026-01-01T00:00:00Z"}'
        )
        (run_dir / "current-step.txt").write_text("- [ ] Step 1: write code\n")
        (run_dir / "last-files.txt").write_text("")
        result = self._run(tmp_path)
        assert result.returncode == 0, f"Script failed: {result.stderr}"
        # Without hash, falls through to last-files check — empty last-files → RESUME_CLEAN
        assert "RESUME_CLEAN" in result.stdout or "RESUME_NONE" in result.stdout


class TestSelectStepBUG1960:
    """BUG-1960: select_step writes task_hash to checkpoint for cross-run detection."""

    def _run(self, tmp_path: Path) -> subprocess.CompletedProcess[str]:
        run_dir = _setup_run_dir(tmp_path)
        script = _load_state_script("select_step")
        script = script.replace("${context.run_dir}", str(run_dir))
        script = script.replace("${context.input_hash}", "abc123def456")
        return _bash(script, cwd=tmp_path)

    def test_checkpoint_contains_task_hash(self, tmp_path: Path) -> None:
        """Fix 3: checkpoint JSON includes task_hash field."""
        import json

        run_dir = _setup_run_dir(tmp_path)
        (run_dir / "plan.md").write_text("# Task Plan\n- [ ] Step 1: write code\n")
        self._run(tmp_path)
        checkpoint = run_dir / "checkpoint.json"
        assert checkpoint.exists()
        data = json.loads(checkpoint.read_text())
        assert "task_hash" in data, (
            "select_step checkpoint must include task_hash for cross-run detection"
        )
        assert data["task_hash"] == "abc123def456"


class TestCheckDoneErrorRoutingBUG1960:
    """BUG-1960: check_done.on_error routes to select_step (recoverable) not diagnose."""

    def test_check_done_on_error_routes_to_select_step(self, raw_data: dict) -> None:
        """Fix 4: on_error: select_step makes missing-capture errors recoverable."""
        check_done = raw_data["states"]["check_done"]
        assert check_done["on_error"] == "select_step", (
            "check_done.on_error must route to select_step so interpolation errors "
            "on ${captured.selected_step.output} recover gracefully instead of "
            "terminating the loop"
        )
