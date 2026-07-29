"""Tests for FSM validation reachability/dominance rule family:
capture-reachability, static loop refs, policy-table dimension scoring, and
progress-paths isolation.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from little_loops.fsm.schema import (
    CircuitConfig,
    EvaluateConfig,
    FSMLoop,
    RepeatedFailureConfig,
    StateConfig,
)
from little_loops.fsm.validation import (
    ValidationSeverity,
    _validate_capture_reachability,
    _validate_policy_dimensions_scored,
    _validate_progress_paths_isolation,
    load_and_validate,
    validate_fsm,
)


def make_state(**kwargs) -> StateConfig:
    """Convenience constructor for StateConfig in tests."""
    return StateConfig(**kwargs)


class TestProgressPathsIsolation:
    """BUG-1767: loops must not list self-written files in progress_paths."""

    def _make_fsm(
        self,
        action: str,
        progress_paths: list[str],
        exclude_paths: list[str] | None = None,
    ) -> FSMLoop:
        return FSMLoop(
            name="test-loop",
            initial="work",
            states={
                "work": make_state(action=action, on_yes="done", on_no="work"),
                "done": make_state(terminal=True),
            },
            circuit=CircuitConfig(
                repeated_failure=RepeatedFailureConfig(
                    progress_paths=progress_paths,
                    exclude_paths=exclude_paths or [],
                )
            ),
        )

    def test_fires_when_action_writes_to_progress_path(self) -> None:
        """WARNING fires when a state action references a progress_paths file."""
        fsm = self._make_fsm(
            action="echo hi >> .loops/tmp/plan.md",
            progress_paths=[".loops/tmp/plan.md"],
        )
        errors = _validate_progress_paths_isolation(fsm)
        assert len(errors) == 1
        assert errors[0].severity == ValidationSeverity.WARNING
        assert ".loops/tmp/plan.md" in errors[0].message
        assert errors[0].path == "states.work.action"

    def test_fires_with_interpolation_prefix_in_progress_paths(self) -> None:
        """WARNING fires even when the progress_path has a ${env.PWD}/ prefix."""
        fsm = self._make_fsm(
            action="echo step >> .loops/tmp/general-task-plan.md",
            progress_paths=["${env.PWD}/.loops/tmp/general-task-plan.md"],
        )
        errors = _validate_progress_paths_isolation(fsm)
        assert len(errors) == 1
        assert ".loops/tmp/general-task-plan.md" in errors[0].message

    def test_does_not_fire_when_no_progress_paths(self) -> None:
        """No WARNING when progress_paths is empty."""
        fsm = self._make_fsm(
            action="echo hi >> .loops/tmp/plan.md",
            progress_paths=[],
        )
        errors = _validate_progress_paths_isolation(fsm)
        assert errors == []

    def test_does_not_fire_when_action_does_not_reference_path(self) -> None:
        """No WARNING when the action does not reference any progress_paths file."""
        fsm = self._make_fsm(
            action="run-my-tool.sh",
            progress_paths=[".loops/tmp/plan.md"],
        )
        errors = _validate_progress_paths_isolation(fsm)
        assert errors == []

    def test_does_not_fire_when_path_is_excluded(self) -> None:
        """No WARNING when the overlapping path is already in exclude_paths."""
        fsm = self._make_fsm(
            action="echo hi >> .loops/tmp/plan.md",
            progress_paths=[".loops/tmp/plan.md"],
            exclude_paths=[".loops/tmp/plan.md"],
        )
        errors = _validate_progress_paths_isolation(fsm)
        assert errors == []

    def test_does_not_fire_when_no_circuit(self) -> None:
        """No WARNING when the loop has no circuit block."""
        fsm = FSMLoop(
            name="test-loop",
            initial="work",
            states={
                "work": make_state(action="echo .loops/tmp/plan.md", on_yes="done"),
                "done": make_state(terminal=True),
            },
        )
        errors = _validate_progress_paths_isolation(fsm)
        assert errors == []

    def test_wired_into_validate_fsm(self) -> None:
        """validate_fsm() surfaces the progress_paths isolation warning end-to-end."""
        fsm = self._make_fsm(
            action="echo hi >> .loops/tmp/plan.md",
            progress_paths=[".loops/tmp/plan.md"],
        )
        errors = validate_fsm(fsm)
        overlap_warnings = [
            e
            for e in errors
            if e.severity == ValidationSeverity.WARNING and "exclude_paths" in e.message
        ]
        assert len(overlap_warnings) == 1


class TestCaptureReachabilityValidation:
    """ENH-1961: static validation of captured variable reachability in FSM validator."""

    # --- Helper to build FSMs for testing ---

    def _fsm_with_capture_and_ref(
        self,
        *,
        capture_state: str = "select",
        capture_var: str = "selected",
        ref_state: str = "check",
        ref_var: str | None = None,
        extra_states: dict | None = None,
        initial: str = "start",
    ) -> FSMLoop:
        """Build a minimal FSM with a capture state and a referencing state.

        Default graph: start → select → check → done
        The capture state captures a variable, the ref state references it.
        extra_states can inject bypass paths or additional routing.
        """
        if ref_var is None:
            ref_var = capture_var

        states: dict[str, StateConfig] = {
            "start": make_state(
                action="echo begin",
                next=capture_state,
            ),
            capture_state: make_state(
                action="echo capturing",
                capture=capture_var,
                next=ref_state,
            ),
            ref_state: make_state(
                action=f"echo ${{{{captured.{ref_var}.output}}}}",
                on_yes="done",
            ),
            "done": make_state(terminal=True),
        }

        if extra_states:
            states.update(extra_states)

        return FSMLoop(
            name="test-capture-reachability",
            initial=initial,
            states=states,
        )

    # --- Dominance: all paths safe → no warning ---

    def test_capture_reachable_on_all_paths_no_warning(self) -> None:
        """No warning when capturing state dominates referencing state."""
        fsm = self._fsm_with_capture_and_ref()
        errors = _validate_capture_reachability(fsm)
        assert errors == [], f"Expected no warnings, got: {errors}"

    def test_capture_with_unconditional_next_safe(self) -> None:
        """No warning when state has next: through capture state (dominated)."""
        fsm = self._fsm_with_capture_and_ref()
        errors = _validate_capture_reachability(fsm)
        assert errors == []

    def test_capture_self_reference_no_warning(self) -> None:
        """State that captures and references its own variable is safe."""
        fsm = FSMLoop(
            name="test-self-ref",
            initial="work",
            states={
                "work": make_state(
                    action="echo ${captured.result.output}",
                    capture="result",
                    on_yes="done",
                ),
                "done": make_state(terminal=True),
            },
        )
        errors = _validate_capture_reachability(fsm)
        assert errors == []

    def test_bypassed_capture_with_default_guard_no_warning(self) -> None:
        """No bypass WARNING when every reference is guarded by `:default=`.

        The interpolation engine substitutes the default when the capture is
        missing, so a guarded reference is safe even on paths that bypass the
        capturing state. Mirrors general-task's check_done references.
        """
        fsm = self._fsm_with_capture_and_ref(
            extra_states={
                "shortcut": make_state(action="echo bypass", next="check"),
            },
        )
        # Fork 'start' so 'check' is reachable via a path that bypasses 'select'.
        fsm.states["start"] = make_state(action="echo begin", on_yes="select", on_no="shortcut")
        # check references the captured var but GUARDS it with :default=.
        fsm.states["check"] = make_state(
            action="echo ${captured.selected.output:default=not-reached}",
            on_yes="done",
        )
        errors = _validate_capture_reachability(fsm)
        assert errors == [], f"Guarded reference should not warn, got: {errors}"

    def test_missing_capture_with_default_guard_no_error(self) -> None:
        """A never-captured var referenced only with `:default=` is not an error.

        `:default=` is the author explicitly opting into 'missing is OK'.
        """
        fsm = FSMLoop(
            name="test-guarded-missing",
            initial="work",
            states={
                "work": make_state(
                    action="echo ${captured.nonexistent.output:default=fallback}",
                    on_yes="done",
                ),
                "done": make_state(terminal=True),
            },
        )
        errors = _validate_capture_reachability(fsm)
        assert errors == [], f"Guarded missing-capture should not error, got: {errors}"

    def test_missing_capture_with_nullable_guard_no_error(self) -> None:
        """BUG-2726: a never-captured var referenced only with the `?` nullable
        suffix is not an error. The interpolation engine resolves a missing `?`
        ref to "", so it is provably safe on bypass paths exactly like `:default=`.
        This is the idiom a shared multi-source diagnose state relies on."""
        fsm = FSMLoop(
            name="test-nullable-missing",
            initial="work",
            states={
                "work": make_state(
                    action="echo ${captured.nonexistent.stderr?}",
                    on_yes="done",
                ),
                "done": make_state(terminal=True),
            },
        )
        errors = _validate_capture_reachability(fsm)
        assert errors == [], f"Nullable missing-capture should not error, got: {errors}"

    def test_mixed_guarded_and_unguarded_still_warns(self) -> None:
        """If ANY reference to a var is unguarded, the bypass WARNING still fires."""
        fsm = self._fsm_with_capture_and_ref(
            extra_states={
                "shortcut": make_state(action="echo bypass", next="check"),
            },
        )
        fsm.states["start"] = make_state(action="echo begin", on_yes="select", on_no="shortcut")
        # One guarded reference AND one unguarded reference to the same var.
        fsm.states["check"] = make_state(
            action=("echo ${captured.selected.output:default=x} and ${captured.selected.output}"),
            on_yes="done",
        )
        errors = _validate_capture_reachability(fsm)
        warnings = [e for e in errors if e.severity == ValidationSeverity.WARNING]
        assert len(warnings) >= 1, f"Unguarded reference should still warn, got: {errors}"
        assert any("selected" in e.message for e in warnings)

    # --- Bypassed capture → WARNING ---

    def test_capture_bypassed_on_one_path_emits_warning(self) -> None:
        """WARNING when a path to ref_state bypasses the capturing state."""
        # Two paths to 'check':
        #   start → select → check  (safe)
        #   start → shortcut → check  (bypasses capture!)
        fsm = self._fsm_with_capture_and_ref(
            extra_states={
                "shortcut": make_state(
                    action="echo bypass",
                    next="check",
                ),
            },
        )
        # Modify 'start' to fork into both paths
        fsm.states["start"] = make_state(
            action="echo begin",
            on_yes="select",
            on_no="shortcut",
        )
        # Make 'check' reference the captured var
        fsm.states["check"] = make_state(
            action="echo ${captured.selected.output}",
            on_yes="done",
        )

        errors = _validate_capture_reachability(fsm)
        warnings = [e for e in errors if e.severity == ValidationSeverity.WARNING]
        assert len(warnings) >= 1, f"Expected bypass WARNING, got: {errors}"
        assert any("selected" in e.message for e in warnings)
        assert any("select" in e.message for e in warnings)

    def test_bypass_path_in_warning_message(self) -> None:
        """Warning message includes a concrete bypassing path."""
        fsm = self._fsm_with_capture_and_ref(
            extra_states={
                "shortcut": make_state(action="echo bypass", next="check"),
            },
        )
        fsm.states["start"] = make_state(
            action="echo begin",
            on_yes="select",
            on_no="shortcut",
        )
        fsm.states["check"] = make_state(
            action="echo ${captured.selected.output}",
            on_yes="done",
        )

        errors = _validate_capture_reachability(fsm)
        warnings = [e for e in errors if e.severity == ValidationSeverity.WARNING]
        assert len(warnings) >= 1
        # The bypass path should be start → shortcut → check
        assert "start" in warnings[0].message
        assert "shortcut" in warnings[0].message
        assert "check" in warnings[0].message

    def test_general_task_pattern_emits_warning(self) -> None:
        """The exact pattern from general-task.yaml (resume bypass) emits warning."""
        # Pattern: resume_check → [yes: mark_done → check_done] / [no: select_step → do_work → check_done]
        # check_done references ${captured.selected_step.output}
        # mark_done path bypasses select_step
        fsm = FSMLoop(
            name="test-general-task-pattern",
            initial="resume_check",
            states={
                "resume_check": make_state(
                    action="check checkpoint",
                    on_yes="mark_done",
                    on_no="select_step",
                ),
                "mark_done": make_state(
                    action="mark done",
                    next="check_done",
                ),
                "select_step": make_state(
                    action="select next step",
                    capture="selected_step",
                    next="do_work",
                ),
                "do_work": make_state(
                    action="do the work",
                    on_yes="check_done",
                ),
                "check_done": make_state(
                    action="check ${captured.selected_step.output}",
                    on_yes="done",
                    on_no="select_step",
                ),
                "done": make_state(terminal=True),
            },
        )
        errors = _validate_capture_reachability(fsm)
        warnings = [e for e in errors if e.severity == ValidationSeverity.WARNING]
        assert len(warnings) >= 1, (
            f"Expected bypass WARNING for general-task pattern, got: {errors}"
        )
        assert any("selected_step" in e.message for e in warnings)
        assert any("select_step" in e.message for e in warnings)
        # Bypass path should be visible
        assert any("mark_done" in e.message for e in warnings)

    # --- Sub-loop states → skipped ---

    def test_capture_from_sub_loop_skipped(self) -> None:
        """State with loop set is skipped (its captured vars live in child namespace)."""
        fsm = FSMLoop(
            name="test-sub-loop-skip",
            initial="delegate",
            states={
                "delegate": make_state(
                    loop="child-loop",
                    action="child-loop",
                    on_yes="done",
                ),
                "done": make_state(terminal=True),
            },
        )
        errors = _validate_capture_reachability(fsm)
        # No capture in this FSM, but delegate references $captured.* in its
        # sub-loop context. We should not emit errors for this.
        missing_errors = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        assert missing_errors == [], f"Sub-loop states should be skipped, got: {missing_errors}"

    # --- ENH-1998: per-variable WARNING in sub-loop context ---

    def test_missing_capture_in_sub_loop_context_emits_warning(self) -> None:
        """ENH-1998: undefined ${captured.*} in a sub-loop loop emits WARNING, not silence."""
        fsm = FSMLoop(
            name="test-sub-loop-missing-warn",
            initial="delegate",
            states={
                "delegate": make_state(
                    loop="child-loop",
                    action="child-loop",
                    on_yes="use_result",
                ),
                "use_result": make_state(
                    action="echo ${captured.typo_var.output}",
                    on_yes="done",
                ),
                "done": make_state(terminal=True),
            },
        )
        errors = _validate_capture_reachability(fsm)
        # Must emit a WARNING (not silent, not ERROR)
        error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        warn_list = [e for e in errors if e.severity == ValidationSeverity.WARNING]
        assert error_list == [], (
            f"Should emit WARNING not ERROR in sub-loop context, got errors: {error_list}"
        )
        assert len(warn_list) >= 1, (
            f"Expected WARNING for undefined capture in sub-loop context, got: {errors}"
        )
        assert any("typo_var" in w.message for w in warn_list)

    def test_captured_var_present_locally_no_warning_with_sub_loop(self) -> None:
        """ENH-1998: locally-captured var in sub-loop loop produces no warning."""
        fsm = FSMLoop(
            name="test-sub-loop-local-capture",
            initial="capture_local",
            states={
                "capture_local": make_state(
                    capture="local_result",
                    action="echo capturing",
                    on_yes="delegate",
                ),
                "delegate": make_state(
                    loop="child-loop",
                    action="child-loop",
                    on_yes="use_local",
                ),
                "use_local": make_state(
                    action="echo ${captured.local_result.output}",
                    on_yes="done",
                ),
                "done": make_state(terminal=True),
            },
        )
        errors = _validate_capture_reachability(fsm)
        # local_result is captured in this FSM — no error or warning for it
        missing = [e for e in errors if "local_result" in e.message]
        assert missing == [], f"Locally-captured var should not be flagged, got: {missing}"

    # --- BUG-2812: nested-path-aware sub-loop capture references ---

    def test_qualified_sub_loop_state_reference_no_warning(self) -> None:
        """${captured.<sub_loop_state>.<var>.<field>} is the correct nested form.

        executor.py merges a child loop's captures under the invoking state's
        own NAME, not any locally-declared `capture:` name. Referencing it via
        the delegating state's name (e.g. examples-miner.yaml's
        `${captured.run_optimizer.gradient.output}`) must not be flagged.
        """
        fsm = FSMLoop(
            name="test-sub-loop-qualified-ref",
            initial="prove",
            states={
                "prove": make_state(
                    loop="oracles/enumerate-and-prove",
                    action="oracles/enumerate-and-prove",
                    on_yes="use_result",
                ),
                "use_result": make_state(
                    action="echo ${captured.prove.targets.output}",
                    on_yes="done",
                ),
                "done": make_state(terminal=True),
            },
        )
        errors = _validate_capture_reachability(fsm)
        assert errors == [], f"Qualified sub-loop-state reference should not be flagged: {errors}"

    def test_sub_loop_delegating_state_own_capture_nested_field_is_error(self) -> None:
        """BUG-2812: `${captured.<own_capture_name>.<field>.output}` is invalid.

        A sub-loop-delegating state's own `capture:` name resolves to the
        child's event-stream dict {"output", "exit_code"} — NOT the child's
        captures. Referencing a nested field beyond that shape (mirroring the
        proof-first-task.yaml `gate_result.extracted.output` bug) must be an
        ERROR, since it can never resolve at runtime.
        """
        fsm = FSMLoop(
            name="test-sub-loop-own-capture-bad-nesting",
            initial="gate",
            states={
                "gate": make_state(
                    loop="assumption-firewall",
                    action="assumption-firewall",
                    capture="gate_result",
                    on_no="check_blocked",
                ),
                "check_blocked": make_state(
                    action="echo ${captured.gate_result.extracted.output}",
                    on_yes="done",
                ),
                "done": make_state(terminal=True),
            },
        )
        errors = _validate_capture_reachability(fsm)
        error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        assert len(error_list) >= 1, f"Expected ERROR for invalid nested field, got: {errors}"
        assert any("gate_result" in e.message and "event stream" in e.message for e in error_list)

    def test_sub_loop_delegating_state_own_capture_output_field_ok(self) -> None:
        """`${captured.<own_capture_name>.output}` is valid — matches the actual
        event-stream shape a sub-loop-delegating state's own capture: exposes.
        """
        fsm = FSMLoop(
            name="test-sub-loop-own-capture-ok",
            initial="gate",
            states={
                "gate": make_state(
                    loop="assumption-firewall",
                    action="assumption-firewall",
                    capture="gate_result",
                    on_yes="check_output",
                ),
                "check_output": make_state(
                    action="echo ${captured.gate_result.output}",
                    on_yes="done",
                ),
                "done": make_state(terminal=True),
            },
        )
        errors = _validate_capture_reachability(fsm)
        assert errors == [], (
            f"Referencing the event-stream's own .output field should be fine: {errors}"
        )

    # --- Missing capture state → ERROR ---

    def test_missing_capture_state_emits_error(self) -> None:
        """ERROR when a ${captured.*} reference has no capturing state at all."""
        fsm = FSMLoop(
            name="test-missing-capture",
            initial="check",
            states={
                "check": make_state(
                    action="echo ${captured.nonexistent.output}",
                    on_yes="done",
                ),
                "done": make_state(terminal=True),
            },
        )
        errors = _validate_capture_reachability(fsm)
        error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        assert len(error_list) >= 1, f"Expected missing-capture ERROR, got: {errors}"
        assert any("nonexistent" in e.message for e in error_list)
        assert any("no state" in e.message.lower() for e in error_list)

    def test_missing_capture_in_evaluate_source_emits_error(self) -> None:
        """ERROR when evaluate.source references uncaptured variable."""
        fsm = FSMLoop(
            name="test-missing-in-source",
            initial="score",
            states={
                "score": make_state(
                    action="echo scoring",
                    evaluate=EvaluateConfig(
                        type="convergence",
                        target=10,
                        source="${captured.baseline.output}",
                        direction="maximize",
                    ),
                    on_yes="done",
                    on_no="score",
                ),
                "done": make_state(terminal=True),
            },
        )
        errors = _validate_capture_reachability(fsm)
        error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        assert len(error_list) >= 1, f"Expected missing-capture ERROR for source ref, got: {errors}"
        assert any("baseline" in e.message for e in error_list)

    # --- Mixed: some safe, some not ---

    def test_multiple_references_mixed_safety(self) -> None:
        """One captured var is safe (dominated), another is bypassed → mixed results."""
        # Graph: start → capture_safe → fork → [yes: capture_risky → ref_state]
        #                                        [no: ref_state]
        # capture_safe dominates ref_state (all paths go through it)
        # capture_risky does NOT dominate ref_state (fork bypasses it)
        fsm = FSMLoop(
            name="test-mixed",
            initial="start",
            states={
                "start": make_state(
                    action="echo begin",
                    next="capture_safe",
                ),
                "capture_safe": make_state(
                    action="echo capturing safe",
                    capture="safe_var",
                    next="fork",
                ),
                "fork": make_state(
                    action="echo forking",
                    on_yes="capture_risky",
                    on_no="ref_state",
                ),
                "capture_risky": make_state(
                    action="echo capturing risky",
                    capture="risky_var",
                    next="ref_state",
                ),
                "ref_state": make_state(
                    action="echo ${captured.safe_var.output} ${captured.risky_var.output}",
                    on_yes="done",
                ),
                "done": make_state(terminal=True),
            },
        )
        errors = _validate_capture_reachability(fsm)
        warnings = [e for e in errors if e.severity == ValidationSeverity.WARNING]
        # risky_var is bypassed (fork.on_no skips capture_risky)
        assert any("risky_var" in e.message for e in warnings), (
            f"Expected risky_var warning, got: {warnings}"
        )
        # safe_var should NOT have a warning — all paths go through capture_safe
        safe_warnings = [e for e in warnings if "safe_var" in e.message]
        assert safe_warnings == [], f"safe_var should be dominated, got: {safe_warnings}"

    # --- No captures → no errors ---

    def test_no_captures_produces_no_errors(self) -> None:
        """Loop with no capture: declarations produces no capture-reachability errors."""
        fsm = FSMLoop(
            name="test-no-captures",
            initial="work",
            states={
                "work": make_state(action="echo hi", on_yes="done"),
                "done": make_state(terminal=True),
            },
        )
        errors = _validate_capture_reachability(fsm)
        assert errors == []

    # --- Wiring ---

    def test_wired_into_validate_fsm(self) -> None:
        """validate_fsm() includes capture-reachability warnings end-to-end."""
        fsm = self._fsm_with_capture_and_ref(
            extra_states={
                "shortcut": make_state(action="echo bypass", next="check"),
            },
        )
        fsm.states["start"] = make_state(
            action="echo begin",
            on_yes="select",
            on_no="shortcut",
        )
        fsm.states["check"] = make_state(
            action="echo ${captured.selected.output}",
            on_yes="done",
        )

        errors = validate_fsm(fsm)
        warnings = [e for e in errors if e.severity == ValidationSeverity.WARNING]
        capture_warnings = [e for e in warnings if "captured" in e.message.lower()]
        assert len(capture_warnings) >= 1, (
            f"Expected capture-reachability warning in validate_fsm output, got: {errors}"
        )

    # --- Additional edge cases ---

    def test_capture_via_evaluate_source_safe_when_dominated(self) -> None:
        """No warning when evaluate.source ref is dominated by its capture state."""
        fsm = FSMLoop(
            name="test-eval-source-safe",
            initial="measure",
            states={
                "measure": make_state(
                    action="echo measuring",
                    capture="baseline",
                    next="score",
                ),
                "score": make_state(
                    action="echo scoring",
                    evaluate=EvaluateConfig(
                        type="convergence",
                        target=10,
                        source="${captured.baseline.output}",
                        direction="maximize",
                    ),
                    on_yes="done",
                    on_no="score",
                ),
                "done": make_state(terminal=True),
            },
        )
        errors = _validate_capture_reachability(fsm)
        assert errors == [], f"Expected no warnings, got: {errors}"

    def test_multiple_capture_states_all_dominate(self) -> None:
        """All capture states dominate the referencing state → no warnings."""
        fsm = FSMLoop(
            name="test-multi-capture-safe",
            initial="step1",
            states={
                "step1": make_state(
                    action="echo step1",
                    capture="result1",
                    next="step2",
                ),
                "step2": make_state(
                    action="echo step2",
                    capture="result2",
                    next="check",
                ),
                "check": make_state(
                    action="echo ${captured.result1.output} ${captured.result2.output}",
                    on_yes="done",
                ),
                "done": make_state(terminal=True),
            },
        )
        errors = _validate_capture_reachability(fsm)
        assert errors == [], f"Expected no warnings, got: {errors}"

    def test_dominance_via_long_path(self) -> None:
        """Dominance through a multi-hop linear path is correctly detected."""
        fsm = FSMLoop(
            name="test-long-path",
            initial="a",
            states={
                "a": make_state(action="echo a", next="b"),
                "b": make_state(action="echo b", capture="data", next="c"),
                "c": make_state(action="echo c", next="d"),
                "d": make_state(action="echo d", next="e"),
                "e": make_state(action="echo ${captured.data.output}", on_yes="done"),
                "done": make_state(terminal=True),
            },
        )
        errors = _validate_capture_reachability(fsm)
        assert errors == [], f"Expected no warnings, got: {errors}"

    def test_alternative_capture_branches_no_warning(self) -> None:
        """Same var captured on both branches of a fork → no warning (rn-implement).

        The rn-implement shape: dequeue_next dispatches to either fifo_pop or
        select_next, both of which capture 'input'. Exactly one runs per tick,
        so the downstream reference is always safe — the validator must treat
        the two capturing states as collective dominators, not pick one.
        """
        fsm = FSMLoop(
            name="test-alt-capture-branches",
            initial="dispatch",
            states={
                "dispatch": make_state(
                    action="echo dispatch",
                    on_yes="branch_a",
                    on_no="branch_b",
                ),
                "branch_a": make_state(
                    action="echo a",
                    capture="input",
                    next="check",
                ),
                "branch_b": make_state(
                    action="echo b",
                    capture="input",
                    next="check",
                ),
                "check": make_state(
                    action="echo ${captured.input.output}",
                    on_yes="done",
                ),
                "done": make_state(terminal=True),
            },
        )
        errors = _validate_capture_reachability(fsm)
        assert errors == [], f"Expected no warnings, got: {errors}"

    def test_partial_capture_branches_still_warn(self) -> None:
        """One fork branch lacks the capture → WARNING still emitted.

        Guards against over-suppression: if only branch_a captures 'input',
        the branch_b path genuinely bypasses the capture and must be flagged.
        """
        fsm = FSMLoop(
            name="test-partial-capture-branches",
            initial="dispatch",
            states={
                "dispatch": make_state(
                    action="echo dispatch",
                    on_yes="branch_a",
                    on_no="branch_b",
                ),
                "branch_a": make_state(
                    action="echo a",
                    capture="input",
                    next="check",
                ),
                "branch_b": make_state(
                    action="echo b",
                    next="check",
                ),
                "check": make_state(
                    action="echo ${captured.input.output}",
                    on_yes="done",
                ),
                "done": make_state(terminal=True),
            },
        )
        errors = _validate_capture_reachability(fsm)
        warnings = [e for e in errors if e.severity == ValidationSeverity.WARNING]
        assert len(warnings) >= 1, f"Expected bypass WARNING, got: {errors}"
        assert any("input" in e.message for e in warnings)
        assert any("branch_b" in e.message for e in warnings)

    # --- ENH-2748: capture_reachability_ok suppress flag ---

    def test_bypass_warning_fires_without_suppress_flag(self) -> None:
        """Sanity: the bypass WARNING fires when capture_reachability_ok is unset."""
        fsm = self._fsm_with_capture_and_ref(
            extra_states={
                "shortcut": make_state(action="echo bypass", next="check"),
            },
        )
        fsm.states["start"] = make_state(action="echo begin", on_yes="select", on_no="shortcut")
        fsm.states["check"] = make_state(
            action="echo ${captured.selected.output}",
            on_yes="done",
        )
        errors = _validate_capture_reachability(fsm)
        assert len(errors) >= 1

    def test_bypass_warning_suppressed_by_capture_reachability_ok(self) -> None:
        """capture_reachability_ok: true suppresses the bypass WARNING entirely."""
        fsm = self._fsm_with_capture_and_ref(
            extra_states={
                "shortcut": make_state(action="echo bypass", next="check"),
            },
        )
        fsm.states["start"] = make_state(action="echo begin", on_yes="select", on_no="shortcut")
        fsm.states["check"] = make_state(
            action="echo ${captured.selected.output}",
            on_yes="done",
        )
        fsm.capture_reachability_ok = True
        errors = _validate_capture_reachability(fsm)
        assert errors == []

    def test_capture_reachability_ok_runs_via_validate_fsm(self) -> None:
        """validate_fsm() wires in the capture_reachability_ok suppression (end-to-end)."""
        fsm = self._fsm_with_capture_and_ref(
            extra_states={
                "shortcut": make_state(action="echo bypass", next="check"),
            },
        )
        fsm.states["start"] = make_state(action="echo begin", on_yes="select", on_no="shortcut")
        fsm.states["check"] = make_state(
            action="echo ${captured.selected.output}",
            on_yes="done",
        )
        fsm.capture_reachability_ok = True
        errors = validate_fsm(fsm)
        capture_warnings = [e for e in errors if "captured.selected" in e.message]
        assert capture_warnings == []

    def test_capture_reachability_ok_recognized_as_top_level_key(self, tmp_path: Path) -> None:
        """A YAML with top-level capture_reachability_ok produces no Unknown-top-level warning."""
        loop_yaml = tmp_path / "loop.yaml"
        loop_yaml.write_text(
            "name: test-loop\n"
            "description: A loop with a reviewed runtime-guarded capture bypass\n"
            "initial: work\n"
            "capture_reachability_ok: true\n"
            "states:\n"
            "  work:\n"
            "    action: run.sh\n"
            "    on_yes: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        _, warnings = load_and_validate(loop_yaml)
        unknown_warnings = [w for w in warnings if "Unknown top-level" in w.message]
        assert unknown_warnings == []


class TestLoopReferenceValidation:
    """BUG-2305 / sprint-refine audit: _validate_loop_references emits ERROR for
    unresolvable static loop: refs (promoted from WARNING — a static ref that fails
    resolution at definition time fails identically at runtime, so it is never benign)."""

    def _write_yaml(self, tmp_path: Path, body: str) -> Path:
        p = tmp_path / "test-loop.yaml"
        p.write_text(body)
        return p

    def test_missing_loop_reference_emits_error(self, tmp_path: Path) -> None:
        """A bare loop: ref with no matching file produces one ERROR."""
        loop_yaml = self._write_yaml(
            tmp_path,
            (
                "name: parent-loop\n"
                "description: test\n"
                "initial: launch\n"
                "states:\n"
                "  launch:\n"
                "    loop: nonexistent-loop\n"
                "    on_complete: done\n"
                "  done:\n"
                "    terminal: true\n"
            ),
        )
        _, diagnostics = load_and_validate(loop_yaml, raise_on_error=False)
        ref_errors = [
            d
            for d in diagnostics
            if d.severity == ValidationSeverity.ERROR and "nonexistent-loop" in d.message
        ]
        assert len(ref_errors) == 1, f"Expected 1 loop-reference error, got: {diagnostics}"
        assert ref_errors[0].path == "states.launch.loop"

    def test_missing_loop_reference_raises_by_default(self, tmp_path: Path) -> None:
        """With raise_on_error=True (the default), an unresolvable loop: ref fails the load."""
        loop_yaml = self._write_yaml(
            tmp_path,
            (
                "name: parent-loop\n"
                "description: test\n"
                "initial: launch\n"
                "states:\n"
                "  launch:\n"
                "    loop: nonexistent-loop\n"
                "    on_complete: done\n"
                "  done:\n"
                "    terminal: true\n"
            ),
        )
        with pytest.raises(ValueError, match="nonexistent-loop"):
            load_and_validate(loop_yaml)

    def test_missing_loop_reference_no_with_block(self, tmp_path: Path) -> None:
        """Bare loop: ref (no with: block) is checked — this was the original gap."""
        loop_yaml = self._write_yaml(
            tmp_path,
            (
                "name: parent-loop\n"
                "description: test\n"
                "initial: run\n"
                "states:\n"
                "  run:\n"
                "    loop: missing-child\n"
                "    on_complete: end\n"
                "  end:\n"
                "    terminal: true\n"
            ),
        )
        _, diagnostics = load_and_validate(loop_yaml, raise_on_error=False)
        ref_warnings = [d for d in diagnostics if "missing-child" in d.message]
        assert ref_warnings, "Expected a warning for unresolvable bare loop: ref"

    def test_resolvable_loop_reference_no_warning(self, tmp_path: Path) -> None:
        """A loop: ref pointing to a real sibling file emits no warning."""
        (tmp_path / "child-loop.yaml").write_text(
            "name: child-loop\ndescription: child\ninitial: done\nstates:\n  done:\n    terminal: true\n"
        )
        loop_yaml = self._write_yaml(
            tmp_path,
            (
                "name: parent-loop\n"
                "description: test\n"
                "initial: run\n"
                "states:\n"
                "  run:\n"
                "    loop: child-loop\n"
                "    on_complete: end\n"
                "  end:\n"
                "    terminal: true\n"
            ),
        )
        _, diagnostics = load_and_validate(loop_yaml, raise_on_error=False)
        ref_warnings = [
            d
            for d in diagnostics
            if d.severity == ValidationSeverity.WARNING and "child-loop" in d.message
        ]
        assert ref_warnings == [], (
            f"Expected no loop-reference warning for resolvable ref, got: {ref_warnings}"
        )


class TestPolicyDimensionsScored:
    """policy_rules predicate dimensions must be scored (ENH-2309)."""

    def _policy_fsm(
        self,
        *,
        policy_rules: str = "",
        rubric_dimensions: str = "",
        shell_scorer_action: str = "",
        policy_dims_scored_ok: bool = False,
    ) -> FSMLoop:
        context: dict = {}
        if policy_rules:
            context["policy_rules"] = policy_rules
        if rubric_dimensions:
            context["rubric_dimensions"] = rubric_dimensions
        states: dict = {
            "work": make_state(action="run.sh", on_yes="done", on_no="done"),
            "done": make_state(terminal=True),
        }
        if shell_scorer_action:
            states["score"] = make_state(action=shell_scorer_action)
        return FSMLoop(
            name="test-loop",
            initial="work",
            states=states,
            context=context,
            policy_dims_scored_ok=policy_dims_scored_ok,
        )

    def test_warning_fires_for_unscored_dim(self) -> None:
        """WARNING fires when a predicate dim is not in rubric_dimensions or shell writes."""
        fsm = self._policy_fsm(
            policy_rules="quality:>=85 -> done\n* -> work",
        )
        errors = _validate_policy_dimensions_scored(fsm)
        assert len(errors) == 1
        assert errors[0].severity == ValidationSeverity.WARNING
        assert "quality" in errors[0].message
        assert "inert" in errors[0].message

    def test_no_warning_when_dim_in_rubric_dimensions(self) -> None:
        """No warning when the predicate dim matches a rubric_dimensions entry."""
        fsm = self._policy_fsm(
            policy_rules="quality:>=85 -> done\n* -> work",
            rubric_dimensions="quality",
        )
        errors = _validate_policy_dimensions_scored(fsm)
        assert errors == []

    def test_no_warning_when_dim_written_by_shell_scorer(self) -> None:
        """No warning when a shell state writes rubric-dim-<name>.txt for the dim."""
        fsm = self._policy_fsm(
            policy_rules="quality:>=85 -> done\n* -> work",
            shell_scorer_action="echo 80 > rubric-dim-quality.txt",
        )
        errors = _validate_policy_dimensions_scored(fsm)
        assert errors == []

    def test_aggregate_exempt(self) -> None:
        """The reserved 'aggregate' dimension never triggers the warning."""
        fsm = self._policy_fsm(
            policy_rules="aggregate:>=85 -> done\n* -> work",
        )
        errors = _validate_policy_dimensions_scored(fsm)
        assert errors == []

    def test_suppressed_by_policy_dims_scored_ok(self) -> None:
        """policy_dims_scored_ok: true suppresses the warning."""
        fsm = self._policy_fsm(
            policy_rules="quality:>=85 -> done\n* -> work",
            policy_dims_scored_ok=True,
        )
        errors = _validate_policy_dimensions_scored(fsm)
        assert errors == []

    def test_no_errors_for_empty_policy_rules(self) -> None:
        """An absent or empty policy_rules block produces no errors."""
        fsm = self._policy_fsm(policy_rules="")
        errors = _validate_policy_dimensions_scored(fsm)
        assert errors == []

    def test_no_crash_on_malformed_policy_rules(self) -> None:
        """A malformed policy_rules block defers to the grammar validator; no crash."""
        fsm = self._policy_fsm(policy_rules="not valid rule syntax!!!")
        errors = _validate_policy_dimensions_scored(fsm)
        assert errors == []

    def test_raw_dim_not_normalized_triggers_warning(self) -> None:
        """Predicate 'Has Citations' stays raw; rubric_dimensions 'Has Citations'
        normalizes to 'has-citations' in the scored set — no match, warning fires."""
        fsm = self._policy_fsm(
            policy_rules="Has Citations:==true -> done\n* -> work",
            rubric_dimensions="Has Citations",
        )
        errors = _validate_policy_dimensions_scored(fsm)
        assert len(errors) == 1
        assert "Has Citations" in errors[0].message

    def test_wired_into_validate_fsm(self) -> None:
        """validate_fsm() includes the policy-dimensions-scored warning."""
        fsm = self._policy_fsm(
            policy_rules="quality:>=85 -> done\n* -> work",
        )
        all_errors = validate_fsm(fsm)
        dim_warnings = [
            e
            for e in all_errors
            if e.severity == ValidationSeverity.WARNING
            and "inert" in e.message
            and e.path == "context.policy_rules"
        ]
        assert len(dim_warnings) == 1

    def test_policy_dims_scored_ok_recognized_as_top_level_key(self, tmp_path: Path) -> None:
        """A YAML with top-level policy_dims_scored_ok produces no Unknown-top-level warning."""
        loop_yaml = tmp_path / "loop.yaml"
        loop_yaml.write_text(
            "name: test-loop\n"
            "description: Loop with intentionally unscored dims\n"
            "initial: work\n"
            "policy_dims_scored_ok: true\n"
            "states:\n"
            "  work:\n"
            "    action: run.sh\n"
            "    on_yes: done\n"
            "    on_no: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        _, warnings = load_and_validate(loop_yaml)
        unknown_warnings = [w for w in warnings if "Unknown top-level" in w.message]
        assert unknown_warnings == []

    def test_canonical_policy_refine_dims_pass(self) -> None:
        """policy-refine's dimensions are all scored — no warning fires."""
        # policy-refine: rubric_dimensions = "clarity|completeness|feasibility|security"
        # policy_rules references: security, completeness, feasibility, clarity, aggregate
        fsm = self._policy_fsm(
            policy_rules=(
                "security:<65 -> escalate\n"
                "completeness:<60 -> deep_repair\n"
                "feasibility:<60 -> rethink\n"
                "clarity:>=85 & completeness:>=85 & feasibility:>=85 -> done\n"
                "aggregate:>=85 -> done\n"
                "aggregate:>=60 -> light_repair\n"
                "* -> deep_repair"
            ),
            rubric_dimensions="clarity|completeness|feasibility|security",
        )
        errors = _validate_policy_dimensions_scored(fsm)
        assert errors == []
