"""Tests for FSM validation logic.

Tests cover reachability analysis and routing validation, including
support for custom on_<verdict> routing via extra_routes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from little_loops.fsm.schema import (
    CircuitConfig,
    EvaluateConfig,
    FSMLoop,
    ParameterSpec,
    RepeatedFailureConfig,
    StateConfig,
    TargetFileSpec,
    ThrottleConfig,
)
from little_loops.fsm.validation import (
    ValidationSeverity,
    _validate_evaluator,
    _validate_meta_loop_evaluation,
    _validate_parameters,
    load_and_validate,
    validate_fsm,
)


def make_state(**kwargs) -> StateConfig:
    """Convenience constructor for StateConfig in tests."""
    return StateConfig(**kwargs)


class TestExtraRoutesReachability:
    """Validate that extra_routes targets are included in reachability BFS."""

    def test_extra_routes_targets_are_reachable(self) -> None:
        """States reachable only via extra_routes are not flagged as unreachable."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": StateConfig(extra_routes={"done": "final", "retry": "check"}),
                "final": make_state(terminal=True),
            },
        )
        errors = validate_fsm(fsm)
        warnings = [e for e in errors if e.severity == ValidationSeverity.WARNING]
        assert not any("not reachable" in e.message for e in warnings)

    def test_no_false_positive_for_custom_on_routing(self) -> None:
        """A state targeted only by on_done is not marked unreachable."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": StateConfig(extra_routes={"done": "final"}),
                "final": make_state(terminal=True),
            },
        )
        errors = validate_fsm(fsm)
        unreachable_warnings = [
            e
            for e in errors
            if e.severity == ValidationSeverity.WARNING and "not reachable" in e.message
        ]
        assert len(unreachable_warnings) == 0

    def test_truly_unreachable_state_still_warned(self) -> None:
        """An orphan state (not referenced by any route) is still warned."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": StateConfig(extra_routes={"done": "final"}),
                "final": make_state(terminal=True),
                "orphan": make_state(action="never", next="final"),
            },
        )
        errors = validate_fsm(fsm)
        warnings = [e for e in errors if e.severity == ValidationSeverity.WARNING]
        assert any("not reachable" in e.message for e in warnings)


class TestDescriptionFieldValidation:
    """ENH-1331: warn when top-level description field is absent."""

    def test_missing_description_emits_warning(self) -> None:
        """FSM without a description: field produces a WARNING."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={"check": make_state(terminal=True)},
        )
        errors = validate_fsm(fsm)
        description_warnings = [
            e
            for e in errors
            if e.severity == ValidationSeverity.WARNING and "description" in e.message.lower()
        ]
        assert len(description_warnings) == 1
        assert description_warnings[0].path == "<root>"
        assert "description" in description_warnings[0].message

    def test_present_description_emits_no_warning(self) -> None:
        """FSM with a description: field produces no description warning."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            description="A test loop with intent text",
            states={"check": make_state(terminal=True)},
        )
        errors = validate_fsm(fsm)
        description_warnings = [
            e
            for e in errors
            if e.severity == ValidationSeverity.WARNING and "No 'description' field" in e.message
        ]
        assert description_warnings == []

    def test_empty_string_description_emits_warning(self) -> None:
        """An empty-string description is still treated as missing."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            description="",
            states={"check": make_state(terminal=True)},
        )
        errors = validate_fsm(fsm)
        description_warnings = [
            e
            for e in errors
            if e.severity == ValidationSeverity.WARNING and "No 'description' field" in e.message
        ]
        assert len(description_warnings) == 1


class TestRateLimitFieldValidation:
    """BUG-1108: paired validation for max_rate_limit_retries / on_rate_limit_exhausted."""

    def test_max_without_on_fails(self) -> None:
        fsm = FSMLoop(
            name="test",
            initial="s",
            states={
                "s": StateConfig(
                    action="run",
                    on_yes="done",
                    on_no="done",
                    max_rate_limit_retries=3,
                ),
                "done": make_state(terminal=True),
            },
        )
        errors = validate_fsm(fsm)
        assert any(
            "max_rate_limit_retries" in e.message and "on_rate_limit_exhausted" in e.message
            for e in errors
        )

    def test_on_without_max_fails(self) -> None:
        fsm = FSMLoop(
            name="test",
            initial="s",
            states={
                "s": StateConfig(
                    action="run",
                    on_yes="done",
                    on_no="done",
                    on_rate_limit_exhausted="done",
                ),
                "done": make_state(terminal=True),
            },
        )
        errors = validate_fsm(fsm)
        assert any(
            "on_rate_limit_exhausted" in e.message and "max_rate_limit_retries" in e.message
            for e in errors
        )

    def test_max_less_than_one_fails(self) -> None:
        fsm = FSMLoop(
            name="test",
            initial="s",
            states={
                "s": StateConfig(
                    action="run",
                    on_yes="done",
                    on_no="done",
                    max_rate_limit_retries=0,
                    on_rate_limit_exhausted="done",
                ),
                "done": make_state(terminal=True),
            },
        )
        errors = validate_fsm(fsm)
        assert any("max_rate_limit_retries" in e.message and ">= 1" in e.message for e in errors)

    def test_backoff_base_less_than_one_fails(self) -> None:
        fsm = FSMLoop(
            name="test",
            initial="s",
            states={
                "s": StateConfig(
                    action="run",
                    on_yes="done",
                    on_no="done",
                    rate_limit_backoff_base_seconds=0,
                ),
                "done": make_state(terminal=True),
            },
        )
        errors = validate_fsm(fsm)
        assert any(
            "rate_limit_backoff_base_seconds" in e.message and ">= 1" in e.message for e in errors
        )

    def test_both_fields_set_passes(self) -> None:
        fsm = FSMLoop(
            name="test",
            initial="s",
            states={
                "s": StateConfig(
                    action="run",
                    on_yes="done",
                    on_no="done",
                    max_rate_limit_retries=3,
                    on_rate_limit_exhausted="done",
                    rate_limit_backoff_base_seconds=30,
                ),
                "done": make_state(terminal=True),
            },
        )
        errors = validate_fsm(fsm)
        rate_errors = [e for e in errors if "rate_limit" in e.message.lower()]
        assert rate_errors == []

    def test_standalone_backoff_base_seconds_passes(self) -> None:
        """rate_limit_backoff_base_seconds is valid on its own (no paired-field requirement)."""
        fsm = FSMLoop(
            name="test",
            initial="s",
            states={
                "s": StateConfig(
                    action="run",
                    on_yes="done",
                    on_no="done",
                    rate_limit_backoff_base_seconds=30,
                ),
                "done": make_state(terminal=True),
            },
        )
        errors = validate_fsm(fsm)
        rate_errors = [e for e in errors if "rate_limit" in e.message.lower()]
        assert rate_errors == []

    # -------------------------------------------------------------------
    # ENH-1132: rate_limit_max_wait_seconds / rate_limit_long_wait_ladder
    # -------------------------------------------------------------------

    def test_max_wait_seconds_less_than_one_fails(self) -> None:
        fsm = FSMLoop(
            name="test",
            initial="s",
            states={
                "s": StateConfig(
                    action="run",
                    on_yes="done",
                    on_no="done",
                    rate_limit_max_wait_seconds=0,
                ),
                "done": make_state(terminal=True),
            },
        )
        errors = validate_fsm(fsm)
        assert any(
            "rate_limit_max_wait_seconds" in e.message and ">= 1" in e.message for e in errors
        )

    def test_long_wait_ladder_empty_fails(self) -> None:
        fsm = FSMLoop(
            name="test",
            initial="s",
            states={
                "s": StateConfig(
                    action="run",
                    on_yes="done",
                    on_no="done",
                    rate_limit_long_wait_ladder=[],
                ),
                "done": make_state(terminal=True),
            },
        )
        errors = validate_fsm(fsm)
        assert any(
            "rate_limit_long_wait_ladder" in e.message and "non-empty" in e.message for e in errors
        )

    def test_long_wait_ladder_zero_entry_fails(self) -> None:
        fsm = FSMLoop(
            name="test",
            initial="s",
            states={
                "s": StateConfig(
                    action="run",
                    on_yes="done",
                    on_no="done",
                    rate_limit_long_wait_ladder=[300, 0, 900],
                ),
                "done": make_state(terminal=True),
            },
        )
        errors = validate_fsm(fsm)
        assert any(
            "rate_limit_long_wait_ladder" in e.message and "positive" in e.message for e in errors
        )

    def test_long_wait_fields_valid_pass(self) -> None:
        fsm = FSMLoop(
            name="test",
            initial="s",
            states={
                "s": StateConfig(
                    action="run",
                    on_yes="done",
                    on_no="done",
                    rate_limit_max_wait_seconds=21600,
                    rate_limit_long_wait_ladder=[300, 900, 1800, 3600],
                ),
                "done": make_state(terminal=True),
            },
        )
        errors = validate_fsm(fsm)
        rate_errors = [e for e in errors if "rate_limit" in e.message.lower()]
        assert rate_errors == []


class TestHarborScorerEvaluatorValidation:
    """Validate that harbor_scorer is accepted by _validate_evaluator."""

    def test_harbor_scorer_valid_config_passes(self) -> None:
        """_validate_evaluator accepts harbor_scorer with no required fields."""
        config = EvaluateConfig(type="harbor_scorer")
        errors = _validate_evaluator("score", config)
        assert errors == []

    def test_harbor_scorer_unknown_type_rejected(self) -> None:
        """_validate_evaluator rejects an unrecognized evaluator type."""
        config = EvaluateConfig(type="harbor_scorer")
        config.type = "unknown_type_xyz"  # type: ignore[assignment]
        errors = _validate_evaluator("score", config)
        assert any("Unknown evaluator type" in e.message for e in errors)


class TestParameterValidation:
    """Validate the parameters: block via _validate_parameters and validate_fsm."""

    def _fsm_with_params(self, parameters: dict) -> FSMLoop:
        return FSMLoop(
            name="test",
            initial="start",
            states={"start": StateConfig(terminal=True)},
            parameters=parameters,
        )

    def test_valid_all_types(self) -> None:
        """All v1 parameter types are accepted."""
        for ptype in ["string", "integer", "number", "boolean", "enum", "path"]:
            spec = ParameterSpec(type=ptype)
            if ptype == "enum":
                spec = ParameterSpec(type="enum", values=["a", "b"])
            fsm = self._fsm_with_params({"p": spec})
            errors = _validate_parameters(fsm)
            assert errors == [], f"type '{ptype}' should be valid"

    def test_unknown_type_rejected(self) -> None:
        """Unknown parameter type produces an error."""
        spec = ParameterSpec(type="unknown_xyz")
        fsm = self._fsm_with_params({"p": spec})
        errors = _validate_parameters(fsm)
        assert any("Unknown parameter type" in e.message for e in errors)

    def test_enum_without_values_rejected(self) -> None:
        """enum type without values list produces an error."""
        spec = ParameterSpec(type="enum")
        fsm = self._fsm_with_params({"p": spec})
        errors = _validate_parameters(fsm)
        assert any("'enum' requires a 'values' list" in e.message for e in errors)

    def test_required_with_default_rejected(self) -> None:
        """required=True with a default is contradictory."""
        spec = ParameterSpec(type="string", required=True, default="oops")
        fsm = self._fsm_with_params({"p": spec})
        errors = _validate_parameters(fsm)
        assert any("required: true" in e.message and "default" in e.message for e in errors)

    def test_no_errors_on_empty_parameters(self) -> None:
        """Loops without parameters: block produce no errors."""
        fsm = self._fsm_with_params({})
        errors = _validate_parameters(fsm)
        assert errors == []

    def test_validate_fsm_calls_validate_parameters(self) -> None:
        """validate_fsm includes parameter errors in its output."""
        spec = ParameterSpec(type="bogus_type")
        fsm = self._fsm_with_params({"p": spec})
        errors = validate_fsm(fsm)
        assert any("Unknown parameter type" in e.message for e in errors)


class TestWithBindingValidation:
    """Validate with: field structural constraints via validate_fsm."""

    def test_with_without_loop_rejected(self) -> None:
        """with: without loop: produces an error."""
        fsm = FSMLoop(
            name="test",
            initial="bad",
            states={
                "bad": StateConfig(
                    action="echo hi",
                    with_={"key": "val"},
                    on_yes="done",
                ),
                "done": StateConfig(terminal=True),
            },
        )
        errors = validate_fsm(fsm)
        assert any("'with' is only valid when 'loop' is set" in e.message for e in errors)

    def test_with_and_context_passthrough_mutually_exclusive(self) -> None:
        """with: + context_passthrough on the same state is an error."""
        fsm = FSMLoop(
            name="test",
            initial="bad",
            states={
                "bad": StateConfig(
                    loop="child",
                    with_={"key": "val"},
                    context_passthrough=True,
                    on_yes="done",
                ),
                "done": StateConfig(terminal=True),
            },
        )
        errors = validate_fsm(fsm)
        assert any(
            "'with' and 'context_passthrough' are mutually exclusive" in e.message for e in errors
        )

    def test_with_on_loop_state_no_error(self) -> None:
        """with: on a state with loop: set is structurally valid."""
        fsm = FSMLoop(
            name="test",
            initial="run",
            states={
                "run": StateConfig(
                    loop="child",
                    with_={"issue_id": "${context.target}"},
                    on_yes="done",
                ),
                "done": StateConfig(terminal=True),
            },
        )
        # Only structural errors — cross-loop binding errors need load_and_validate
        errors = [
            e for e in validate_fsm(fsm) if "'with'" in e.message and e.severity.value == "error"
        ]
        assert errors == []

    def test_with_context_passthrough_error_avoids_no_transition_phrase(self) -> None:
        """Mutual-exclusion error message does not contain 'no transition'."""
        fsm = FSMLoop(
            name="test",
            initial="bad",
            states={
                "bad": StateConfig(
                    loop="child",
                    with_={"k": "v"},
                    context_passthrough=True,
                    on_yes="done",
                ),
                "done": StateConfig(terminal=True),
            },
        )
        errors = validate_fsm(fsm)
        assert not any("no transition" in e.message.lower() for e in errors)


class TestThrottleValidation:
    """Tests for throttle field validation (ENH-1115)."""

    def _make_fsm(self, throttle: ThrottleConfig) -> FSMLoop:
        return FSMLoop(
            name="test",
            initial="work",
            states={
                "work": StateConfig(
                    action="run.sh",
                    on_yes="done",
                    throttle=throttle,
                ),
                "done": StateConfig(terminal=True),
            },
        )

    def test_valid_throttle_no_errors(self) -> None:
        fsm = self._make_fsm(ThrottleConfig(normal_max=3, warn_max=8, hard_max=12))
        errors = validate_fsm(fsm)
        throttle_errors = [e for e in errors if "throttle" in e.message.lower()]
        assert throttle_errors == []

    def test_warn_max_must_be_greater_than_normal_max(self) -> None:
        fsm = self._make_fsm(ThrottleConfig(normal_max=8, warn_max=5, hard_max=12))
        errors = validate_fsm(fsm)
        assert any("normal_max" in e.message and "warn_max" in e.message for e in errors)

    def test_hard_max_must_be_greater_than_warn_max(self) -> None:
        fsm = self._make_fsm(ThrottleConfig(warn_max=10, hard_max=5))
        errors = validate_fsm(fsm)
        assert any("warn_max" in e.message and "hard_max" in e.message for e in errors)

    def test_non_positive_normal_max_rejected(self) -> None:
        fsm = self._make_fsm(ThrottleConfig(normal_max=0))
        errors = validate_fsm(fsm)
        assert any("normal_max" in e.message for e in errors)

    def test_non_positive_warn_max_rejected(self) -> None:
        fsm = self._make_fsm(ThrottleConfig(warn_max=0))
        errors = validate_fsm(fsm)
        assert any("warn_max" in e.message for e in errors)

    def test_partial_throttle_valid(self) -> None:
        """A throttle with only warn_max set is valid (others use defaults)."""
        fsm = self._make_fsm(ThrottleConfig(warn_max=6))
        errors = validate_fsm(fsm)
        throttle_errors = [e for e in errors if "throttle" in e.message.lower()]
        assert throttle_errors == []


class TestTargetsValidation:
    """ENH-1552: validate_fsm rejects targets[].file values that are not .yaml."""

    def _make_fsm(self, targets: list[TargetFileSpec]) -> FSMLoop:
        return FSMLoop(
            name="test",
            initial="s",
            states={
                "s": make_state(terminal=True),
            },
            targets=targets,
        )

    def test_non_yaml_file_rejected(self) -> None:
        fsm = self._make_fsm([TargetFileSpec(file="loops/harness-optimize.txt")])
        errors = validate_fsm(fsm)
        assert any(
            "targets[0].file" in e.message or "targets[0].file" in (e.path or "") for e in errors
        )

    def test_yaml_file_accepted(self) -> None:
        fsm = self._make_fsm([TargetFileSpec(file="loops/harness-optimize.yaml")])
        errors = validate_fsm(fsm)
        target_errors = [e for e in errors if "targets" in (e.path or "")]
        assert target_errors == []

    def test_glob_only_accepted(self) -> None:
        fsm = self._make_fsm([TargetFileSpec(glob="loops/*.yaml")])
        errors = validate_fsm(fsm)
        target_errors = [e for e in errors if "targets" in (e.path or "")]
        assert target_errors == []

    def test_empty_targets_no_errors(self) -> None:
        fsm = self._make_fsm([])
        errors = validate_fsm(fsm)
        target_errors = [e for e in errors if "targets" in (e.path or "")]
        assert target_errors == []

    def test_error_message_contains_offending_value(self) -> None:
        fsm = self._make_fsm([TargetFileSpec(file="not-yaml.json")])
        errors = validate_fsm(fsm)
        assert any("not-yaml.json" in e.message for e in errors)


class TestCircuitValidation:
    """FEAT-1637: validation for circuit.repeated_failure."""

    def _make_fsm(self, repeated_failure: RepeatedFailureConfig) -> FSMLoop:
        return FSMLoop(
            name="test",
            initial="work",
            states={
                "work": make_state(action="run.sh", on_yes="done"),
                "done": make_state(terminal=True),
                "recover": make_state(terminal=True),
            },
            circuit=CircuitConfig(repeated_failure=repeated_failure),
        )

    def _write_yaml(self, tmp_path: Path, body: str) -> Path:
        p = tmp_path / "loop.yaml"
        p.write_text(body)
        return p

    def test_circuit_recognized_as_top_level_key(self, tmp_path: Path) -> None:
        """A YAML with top-level `circuit:` produces no Unknown-top-level warning."""
        loop_yaml = self._write_yaml(
            tmp_path,
            (
                "name: test-loop\n"
                "description: A loop with circuit block\n"
                "initial: work\n"
                "states:\n"
                "  work:\n"
                "    action: run.sh\n"
                "    on_yes: done\n"
                "  done:\n"
                "    terminal: true\n"
                "circuit:\n"
                "  repeated_failure:\n"
                "    window: 3\n"
                "    on_repeated_failure: abort\n"
            ),
        )
        _, warnings = load_and_validate(loop_yaml)
        unknown_warnings = [w for w in warnings if "Unknown top-level" in w.message]
        assert unknown_warnings == []

    def test_on_repeated_failure_unknown_state_rejected(self, tmp_path: Path) -> None:
        loop_yaml = self._write_yaml(
            tmp_path,
            (
                "name: test-loop\n"
                "description: t\n"
                "initial: work\n"
                "states:\n"
                "  work:\n"
                "    action: run.sh\n"
                "    on_yes: done\n"
                "  done:\n"
                "    terminal: true\n"
                "circuit:\n"
                "  repeated_failure:\n"
                "    on_repeated_failure: ghost_state\n"
            ),
        )
        with pytest.raises(ValueError, match="ghost_state"):
            load_and_validate(loop_yaml)

    def test_on_repeated_failure_abort_accepted(self) -> None:
        fsm = self._make_fsm(RepeatedFailureConfig(window=3, on_repeated_failure="abort"))
        errors = [e for e in validate_fsm(fsm) if e.severity == ValidationSeverity.ERROR]
        circuit_errors = [e for e in errors if "circuit" in (e.path or "")]
        assert circuit_errors == []

    def test_on_repeated_failure_declared_state_accepted(self) -> None:
        fsm = self._make_fsm(RepeatedFailureConfig(window=3, on_repeated_failure="recover"))
        errors = [e for e in validate_fsm(fsm) if e.severity == ValidationSeverity.ERROR]
        circuit_errors = [e for e in errors if "circuit" in (e.path or "")]
        assert circuit_errors == []

    def test_window_must_be_positive(self) -> None:
        fsm = self._make_fsm(RepeatedFailureConfig(window=0, on_repeated_failure="abort"))
        errors = validate_fsm(fsm)
        assert any(
            "circuit.repeated_failure.window" in (e.path or "") and "must be >= 1" in e.message
            for e in errors
        )

    def test_progress_paths_with_circuit_recognized_no_warning(self, tmp_path: Path) -> None:
        """progress_paths under repeated_failure produces no unknown-key warnings (BUG-1674)."""
        loop_yaml = self._write_yaml(
            tmp_path,
            (
                "name: test-loop\n"
                "description: A loop with progress_paths\n"
                "initial: work\n"
                "states:\n"
                "  work:\n"
                "    action: run.sh\n"
                "    on_yes: done\n"
                "  done:\n"
                "    terminal: true\n"
                "circuit:\n"
                "  repeated_failure:\n"
                "    window: 3\n"
                "    on_repeated_failure: abort\n"
                "    progress_paths:\n"
                "      - '${env.PWD}/.loops/tmp/plan.md'\n"
                "      - '${env.PWD}/.loops/tmp/dod.md'\n"
            ),
        )
        _, warnings = load_and_validate(loop_yaml)
        unknown_warnings = [
            w for w in warnings if "Unknown" in w.message or "additional" in w.message.lower()
        ]
        assert unknown_warnings == []


BUILTIN_LOOPS_DIR = Path(__file__).parent.parent / "little_loops" / "loops"


class TestMetaLoopValidation:
    """ENH-1665: MR-1 and MR-2 validation rules for meta-loops."""

    def _meta_fsm(self, **kwargs) -> FSMLoop:
        """Build a minimal meta-loop (detected via lib/benchmark.yaml import)."""
        defaults: dict = {
            "name": "test-meta",
            "initial": "optimize",
            "states": {
                "optimize": make_state(action="run.sh", on_yes="done"),
                "done": make_state(terminal=True),
            },
            "imports": ["lib/benchmark.yaml"],
        }
        defaults.update(kwargs)
        return FSMLoop(**defaults)

    # --- positive control ---

    def test_harness_optimize_passes_clean(self) -> None:
        """harness-optimize.yaml validates without MR-1 or MR-2 errors (positive control)."""
        harness_path = BUILTIN_LOOPS_DIR / "harness-optimize.yaml"
        if not harness_path.exists():
            pytest.skip("harness-optimize.yaml not found in builtin loops")
        fsm, _ = load_and_validate(harness_path)
        errors = _validate_meta_loop_evaluation(fsm)
        mr_errors = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        assert mr_errors == [], f"harness-optimize triggered MR-1: {mr_errors}"
        mr_warnings = [e for e in errors if "MR-2" in e.message or "baseline" in e.message]
        assert mr_warnings == [], f"harness-optimize triggered MR-2: {mr_warnings}"

    # --- MR-1: meta-loop must have non-LLM evaluator ---

    def test_mr1_fires_for_meta_loop_with_only_llm_evaluator(self) -> None:
        """MR-1 ERROR fires when meta-loop uses only llm_structured evaluator."""
        fsm = self._meta_fsm(
            states={
                "check": make_state(
                    action="run.sh",
                    evaluate=EvaluateConfig(type="llm_structured"),
                    on_yes="done",
                    on_no="check",
                ),
                "done": make_state(terminal=True),
            }
        )
        errors = _validate_meta_loop_evaluation(fsm)
        mr1_errors = [
            e for e in errors if e.severity == ValidationSeverity.ERROR and "non-LLM" in e.message
        ]
        assert len(mr1_errors) == 1, f"Expected one MR-1 ERROR, got: {errors}"

    def test_mr1_passes_when_exit_code_evaluator_present(self) -> None:
        """MR-1 does not fire when at least one exit_code evaluator is present."""
        fsm = self._meta_fsm(
            states={
                "check": make_state(
                    action="run.sh",
                    evaluate=EvaluateConfig(type="exit_code"),
                    on_yes="done",
                    on_no="check",
                ),
                "done": make_state(terminal=True),
            }
        )
        errors = _validate_meta_loop_evaluation(fsm)
        mr1_errors = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        assert mr1_errors == [], f"Unexpected MR-1 ERROR: {mr1_errors}"

    def test_mr1_suppressed_by_meta_self_eval_ok(self) -> None:
        """meta_self_eval_ok: true suppresses MR-1."""
        fsm = self._meta_fsm(
            meta_self_eval_ok=True,
            states={
                "check": make_state(
                    action="run.sh",
                    evaluate=EvaluateConfig(type="llm_structured"),
                    on_yes="done",
                    on_no="check",
                ),
                "done": make_state(terminal=True),
            },
        )
        errors = _validate_meta_loop_evaluation(fsm)
        assert errors == [], f"meta_self_eval_ok should suppress all MR errors: {errors}"

    # --- MR-2: meta-loop should have measure-then-act spine ---

    def test_mr2_fires_when_no_capture_referenced_in_evaluate(self) -> None:
        """MR-2 WARNING fires when meta-loop has captures but none referenced in evaluate."""
        fsm = self._meta_fsm(
            states={
                "measure": make_state(
                    action_type="shell",
                    action="./score.sh",
                    capture="baseline",
                    next="check",
                ),
                "check": make_state(
                    action="run.sh",
                    evaluate=EvaluateConfig(type="exit_code"),
                    on_yes="done",
                    on_no="check",
                ),
                "done": make_state(terminal=True),
            }
        )
        errors = _validate_meta_loop_evaluation(fsm)
        mr2_warnings = [
            e
            for e in errors
            if e.severity == ValidationSeverity.WARNING and "baseline" in e.message
        ]
        assert len(mr2_warnings) == 1, f"Expected one MR-2 WARNING, got: {errors}"

    def test_mr2_does_not_fire_when_capture_referenced_in_previous(self) -> None:
        """MR-2 does not fire when captured variable is referenced in evaluate.previous."""
        fsm = self._meta_fsm(
            states={
                "measure": make_state(
                    action_type="shell",
                    action="./score.sh",
                    capture="baseline",
                    next="gate",
                ),
                "gate": make_state(
                    action_type="shell",
                    action="./score.sh",
                    evaluate=EvaluateConfig(
                        type="convergence",
                        target="${context.target_score}",
                        previous="${captured.baseline.output}",
                        direction="maximize",
                    ),
                    route={"target": "done", "progress": "done", "stall": "done"},
                ),
                "done": make_state(terminal=True),
            }
        )
        errors = _validate_meta_loop_evaluation(fsm)
        mr2_warnings = [
            e
            for e in errors
            if e.severity == ValidationSeverity.WARNING and "baseline" in e.message
        ]
        assert mr2_warnings == [], f"Unexpected MR-2 WARNING: {mr2_warnings}"

    def test_mr2_suppressed_by_meta_self_eval_ok(self) -> None:
        """meta_self_eval_ok: true suppresses MR-2."""
        fsm = self._meta_fsm(
            meta_self_eval_ok=True,
            states={
                "measure": make_state(
                    action_type="shell", action="./score.sh", capture="baseline", next="check"
                ),
                "check": make_state(
                    action="run.sh",
                    evaluate=EvaluateConfig(type="exit_code"),
                    on_yes="done",
                    on_no="check",
                ),
                "done": make_state(terminal=True),
            },
        )
        errors = _validate_meta_loop_evaluation(fsm)
        assert errors == []

    # --- non-meta loops are unaffected ---

    def test_non_meta_loop_with_llm_only_not_flagged(self) -> None:
        """A non-meta loop with only llm_structured evaluator does not trigger MR-1 or MR-2."""
        fsm = FSMLoop(
            name="regular-loop",
            initial="check",
            states={
                "check": make_state(
                    action="/ll:some-skill",
                    evaluate=EvaluateConfig(type="llm_structured"),
                    on_yes="done",
                    on_no="check",
                ),
                "done": make_state(terminal=True),
            },
        )
        errors = _validate_meta_loop_evaluation(fsm)
        assert errors == [], f"Non-meta loop should not trigger MR rules: {errors}"

    # --- meta_self_eval_ok round-trip via validate_fsm ---

    def test_meta_self_eval_ok_recognized_as_top_level_key(self, tmp_path: Path) -> None:
        """A YAML with top-level meta_self_eval_ok produces no Unknown-top-level warning."""
        loop_yaml = tmp_path / "loop.yaml"
        loop_yaml.write_text(
            "name: test-loop\n"
            "description: A meta-loop with escape hatch\n"
            "initial: work\n"
            "meta_self_eval_ok: true\n"
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


class TestOnMaxIterationsValidation:
    """Tests for ENH-1631: on_max_iterations validation."""

    _YAML_TEMPLATE = (
        "name: test-loop\n"
        "description: test\n"
        "initial: work\n"
        "states:\n"
        "  work:\n"
        "    action: run.sh\n"
        "    on_yes: done\n"
        "  done:\n"
        "    terminal: true\n"
        "  summarize:\n"
        "    action: summarize.sh\n"
        "    next: done\n"
    )

    def test_on_max_iterations_recognized_as_top_level_key(self, tmp_path: Path) -> None:
        """A YAML with top-level on_max_iterations produces no Unknown-top-level warning."""
        loop_yaml = tmp_path / "loop.yaml"
        loop_yaml.write_text(self._YAML_TEMPLATE + "on_max_iterations: summarize\n")
        _, warnings = load_and_validate(loop_yaml)
        unknown_warnings = [w for w in warnings if "Unknown top-level" in w.message]
        assert unknown_warnings == []

    def test_on_max_iterations_unknown_state_rejected(self) -> None:
        """on_max_iterations pointing to a non-existent state raises ValueError."""
        fsm = FSMLoop(
            name="test",
            initial="work",
            on_max_iterations="ghost_state",
            states={
                "work": StateConfig(action="run.sh", on_yes="done", on_no="work"),
                "done": StateConfig(terminal=True),
            },
        )
        errors = [e for e in validate_fsm(fsm) if e.severity == ValidationSeverity.ERROR]
        assert any("ghost_state" in e.message for e in errors)

    def test_on_max_iterations_valid_state_passes(self) -> None:
        """on_max_iterations pointing to a declared state produces no validation errors."""
        fsm = FSMLoop(
            name="test",
            initial="work",
            on_max_iterations="summarize",
            states={
                "work": StateConfig(action="run.sh", on_yes="done", on_no="work"),
                "summarize": StateConfig(action="summarize.sh", next="done"),
                "done": StateConfig(terminal=True),
            },
        )
        errors = [e for e in validate_fsm(fsm) if e.severity == ValidationSeverity.ERROR]
        on_max_errors = [e for e in errors if "on_max_iterations" in (e.path or "")]
        assert on_max_errors == []
