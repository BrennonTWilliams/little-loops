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
    LearningConfig,
    ParameterSpec,
    RepeatedFailureConfig,
    StateConfig,
    TargetFileSpec,
    ThrottleConfig,
)
from little_loops.fsm.validation import (
    ValidationSeverity,
    _validate_artifact_isolation,
    _validate_evaluator,
    _validate_harness_multimodal_evaluator_blind_spot,
    _validate_input_key_without_guard,
    _validate_meta_loop_evaluation,
    _validate_parameters,
    _validate_partial_route_dead_end,
    _validate_progress_paths_isolation,
    _validate_state_action,
    _validate_zero_retry_counter,
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


class TestActionStallEvaluatorValidation:
    """Validate that action_stall evaluator config is accepted and validated."""

    def test_valid_config_passes(self) -> None:
        """_validate_evaluator accepts action_stall with no required fields."""
        config = EvaluateConfig(type="action_stall")
        errors = _validate_evaluator("check", config)
        assert errors == []

    def test_with_track_and_max_repeat_passes(self) -> None:
        """_validate_evaluator accepts action_stall with track and max_repeat."""
        config = EvaluateConfig(type="action_stall", track=["action", "output"], max_repeat=3)
        errors = _validate_evaluator("check", config)
        assert errors == []

    def test_max_repeat_zero_rejected(self) -> None:
        """max_repeat=0 is rejected."""
        config = EvaluateConfig(type="action_stall", max_repeat=0)
        errors = _validate_evaluator("check", config)
        assert any("max_repeat" in e.message for e in errors)

    def test_max_repeat_negative_rejected(self) -> None:
        """max_repeat=-1 is rejected."""
        config = EvaluateConfig(type="action_stall", max_repeat=-1)
        errors = _validate_evaluator("check", config)
        assert any("max_repeat" in e.message for e in errors)


class TestComparatorEvaluatorValidation:
    """Validate comparator evaluator type registration and MR-1 behavior."""

    def test_comparator_valid_config_passes(self) -> None:
        """_validate_evaluator accepts comparator with baseline_path set."""
        config = EvaluateConfig(type="comparator", baseline_path=".loops/baselines/test/")
        errors = _validate_evaluator("compare", config)
        assert errors == []

    def test_comparator_requires_baseline_path(self) -> None:
        """_validate_evaluator rejects comparator missing baseline_path."""
        config = EvaluateConfig(type="comparator")
        errors = _validate_evaluator("compare", config)
        assert any("baseline_path" in e.message for e in errors)

    def test_mr1_fires_for_meta_loop_with_only_comparator_evaluator(self) -> None:
        """MR-1 fires when meta-loop has only a comparator evaluator (comparator calls the LLM)."""
        from little_loops.fsm.schema import RouteConfig

        # yaml_state_editor in the action triggers meta-loop classification (_META_LOOP_ACTION_TOKENS)
        loop = FSMLoop(
            name="test-meta-loop",
            description="meta loop test",
            initial="check",
            states={
                "check": StateConfig(
                    action="yaml_state_editor loops/some-loop.yaml",
                    evaluate=EvaluateConfig(
                        type="comparator",
                        baseline_path=".loops/baselines/test/",
                    ),
                    route=RouteConfig(routes={"yes": "done", "no": "check"}),
                ),
                "done": StateConfig(action="echo done"),
            },
        )
        errors = validate_fsm(loop)
        mr1_errors = [e for e in errors if "non-LLM evaluator" in e.message]
        assert len(mr1_errors) >= 1, "MR-1 should fire for comparator-only meta-loop"


class TestContractEvaluatorValidation:
    """Validate contract evaluator type registration and MR-1 behavior."""

    def test_contract_valid_config_passes(self) -> None:
        """_validate_evaluator accepts contract with pairs set."""
        config = EvaluateConfig(
            type="contract",
            pairs=[{"producer": "api.ts", "consumer": "hook.ts", "contract": "must match"}],
        )
        errors = _validate_evaluator("check_contract", config)
        assert errors == []

    def test_contract_requires_pairs(self) -> None:
        """_validate_evaluator rejects contract missing pairs."""
        config = EvaluateConfig(type="contract")
        errors = _validate_evaluator("check_contract", config)
        assert any("pairs" in e.message for e in errors)

    def test_mr1_fires_for_meta_loop_with_only_contract_evaluator(self) -> None:
        """MR-1 fires when meta-loop has only a contract evaluator (contract calls the LLM)."""
        from little_loops.fsm.schema import RouteConfig

        loop = FSMLoop(
            name="test-meta-loop",
            description="meta loop test",
            initial="check",
            states={
                "check": StateConfig(
                    action="yaml_state_editor loops/some-loop.yaml",
                    evaluate=EvaluateConfig(
                        type="contract",
                        pairs=[{"producer": "api.ts", "consumer": "hook.ts", "contract": "match"}],
                    ),
                    route=RouteConfig(routes={"yes": "done", "no": "check"}),
                ),
                "done": StateConfig(action="echo done"),
            },
        )
        errors = validate_fsm(loop)
        mr1_errors = [e for e in errors if "non-LLM evaluator" in e.message]
        assert len(mr1_errors) >= 1, "MR-1 should fire for contract-only meta-loop"


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


class TestArtifactIsolation:
    """MR-3: loops must isolate artifacts to ${context.run_dir}, not shared .loops/tmp/."""

    def _simple_fsm(self, action: str, *, shared_state_ok: bool = False) -> FSMLoop:
        return FSMLoop(
            name="test-loop",
            initial="work",
            states={
                "work": make_state(action=action, on_yes="done", on_no="work"),
                "done": make_state(terminal=True),
            },
            shared_state_ok=shared_state_ok,
        )

    def test_mr3_fires_when_loop_writes_to_shared_tmp(self) -> None:
        """MR-3 WARNING fires for any state action referencing .loops/tmp/<path>."""
        fsm = self._simple_fsm("echo hi > .loops/tmp/queue.txt")
        errors = _validate_artifact_isolation(fsm)
        assert len(errors) == 1
        assert errors[0].severity == ValidationSeverity.WARNING
        assert ".loops/tmp/queue.txt" in errors[0].message
        assert errors[0].path == "states.work.action"

    def test_mr3_does_not_fire_when_loop_uses_context_run_dir(self) -> None:
        """MR-3 does not fire when the action uses ${context.run_dir} for artifacts."""
        fsm = self._simple_fsm('echo hi > "${context.run_dir}/queue.txt"')
        errors = _validate_artifact_isolation(fsm)
        assert errors == []

    def test_mr3_does_not_fire_for_issues_dir(self) -> None:
        """MR-3 does not fire for legitimate .issues/ writes."""
        fsm = self._simple_fsm("echo content > .issues/bugs/new.md")
        errors = _validate_artifact_isolation(fsm)
        assert errors == []

    def test_mr3_does_not_fire_for_diagnostics_dir(self) -> None:
        """MR-3 does not fire for legitimate .loops/diagnostics/ writes."""
        fsm = self._simple_fsm("echo log > .loops/diagnostics/report.md")
        errors = _validate_artifact_isolation(fsm)
        assert errors == []

    def test_mr3_does_not_fire_for_actionless_states(self) -> None:
        """States without an action (e.g., terminal or sub-loop states) do not trigger MR-3."""
        fsm = FSMLoop(
            name="test-loop",
            initial="s",
            states={"s": make_state(terminal=True)},
        )
        errors = _validate_artifact_isolation(fsm)
        assert errors == []

    def test_mr3_fires_once_per_occurrence(self) -> None:
        """An action with multiple shared-tmp paths emits one warning per path."""
        fsm = self._simple_fsm("cat .loops/tmp/a.txt > .loops/tmp/b.txt && rm .loops/tmp/c.txt")
        errors = _validate_artifact_isolation(fsm)
        assert len(errors) == 3
        matched = sorted(e.message.split("'")[1] for e in errors)
        assert matched == [".loops/tmp/a.txt", ".loops/tmp/b.txt", ".loops/tmp/c.txt"]

    def test_mr3_suppressed_by_shared_state_ok(self) -> None:
        """shared_state_ok: true suppresses MR-3 entirely."""
        fsm = self._simple_fsm("echo hi > .loops/tmp/queue.txt", shared_state_ok=True)
        errors = _validate_artifact_isolation(fsm)
        assert errors == []

    def test_mr3_runs_via_validate_fsm(self) -> None:
        """validate_fsm() wires in MR-3 (end-to-end, not just direct call)."""
        fsm = self._simple_fsm("echo hi > .loops/tmp/queue.txt")
        errors = validate_fsm(fsm)
        mr3 = [
            e
            for e in errors
            if e.severity == ValidationSeverity.WARNING and ".loops/tmp/queue.txt" in e.message
        ]
        assert len(mr3) == 1

    def test_shared_state_ok_recognized_as_top_level_key(self, tmp_path: Path) -> None:
        """A YAML with top-level shared_state_ok produces no Unknown-top-level warning."""
        loop_yaml = tmp_path / "loop.yaml"
        loop_yaml.write_text(
            "name: test-loop\n"
            "description: A loop that intentionally shares cross-run state\n"
            "initial: work\n"
            "shared_state_ok: true\n"
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


class TestPartialRouteDeadEnd:
    """MR-4 (ENH-1917): LLM-judged states with only on_yes have a partial/no dead-end."""

    def _prompt_fsm(
        self,
        *,
        on_yes: str | None = "done",
        on_no: str | None = None,
        on_partial: str | None = None,
        next_state: str | None = None,
        action_type: str | None = "prompt",
        partial_route_ok: bool = False,
        with_route: bool = False,
    ) -> FSMLoop:
        state_kwargs: dict = {
            "action": "Do something",
            "on_error": "failed",
        }
        if action_type is not None:
            state_kwargs["action_type"] = action_type
        if on_yes is not None:
            state_kwargs["on_yes"] = on_yes
        if on_no is not None:
            state_kwargs["on_no"] = on_no
        if on_partial is not None:
            state_kwargs["on_partial"] = on_partial
        if next_state is not None:
            state_kwargs["next"] = next_state
        if with_route:
            from little_loops.fsm.schema import RouteConfig

            state_kwargs.pop("on_yes", None)
            state_kwargs["route"] = RouteConfig(routes={"yes": "done"}, default="done")
        return FSMLoop(
            name="test-loop",
            initial="generate",
            states={
                "generate": make_state(**state_kwargs),
                "done": make_state(terminal=True),
                "failed": make_state(terminal=True),
            },
            partial_route_ok=partial_route_ok,
        )

    # --- positive controls ---

    def test_mr4_fires_for_on_yes_only_prompt_state(self) -> None:
        """MR-4 WARNING fires when a prompt state has only on_yes with no on_no/on_partial."""
        fsm = self._prompt_fsm()
        errors = _validate_partial_route_dead_end(fsm)
        assert len(errors) == 1
        assert errors[0].severity == ValidationSeverity.WARNING
        assert "generate" in errors[0].message
        assert "ENH-1917" in errors[0].message
        assert errors[0].path == "states.generate"

    def test_mr4_fires_when_on_partial_missing(self) -> None:
        """MR-4 fires when on_no is set but on_partial is missing."""
        fsm = self._prompt_fsm(on_no="generate")
        errors = _validate_partial_route_dead_end(fsm)
        assert len(errors) == 1
        assert "`partial`" in errors[0].message

    def test_mr4_fires_when_on_no_missing(self) -> None:
        """MR-4 fires when on_partial is set but on_no is missing."""
        fsm = self._prompt_fsm(on_partial="generate")
        errors = _validate_partial_route_dead_end(fsm)
        assert len(errors) == 1
        assert "`no`" in errors[0].message

    def test_mr4_fires_for_slash_command_action_type(self) -> None:
        """MR-4 fires for slash_command action_type, not just prompt."""
        fsm = self._prompt_fsm(action_type="slash_command")
        errors = _validate_partial_route_dead_end(fsm)
        assert len(errors) == 1

    def test_mr4_fires_for_implicit_prompt_via_slash_prefix(self) -> None:
        """MR-4 fires for a /slash action with no explicit action_type."""
        fsm = FSMLoop(
            name="test-loop",
            initial="run",
            states={
                "run": make_state(action="/ll:some-skill", on_yes="done", on_error="failed"),
                "done": make_state(terminal=True),
                "failed": make_state(terminal=True),
            },
        )
        errors = _validate_partial_route_dead_end(fsm)
        assert len(errors) == 1

    # --- negative controls ---

    def test_mr4_does_not_fire_when_on_no_and_on_partial_both_set(self) -> None:
        """No warning when both on_no and on_partial are mapped."""
        fsm = self._prompt_fsm(on_no="generate", on_partial="generate")
        errors = _validate_partial_route_dead_end(fsm)
        assert errors == []

    def test_mr4_does_not_fire_when_next_present(self) -> None:
        """No warning when next: provides an unconditional handoff."""
        fsm = self._prompt_fsm(on_yes=None, next_state="done")
        errors = _validate_partial_route_dead_end(fsm)
        assert errors == []

    def test_mr4_does_not_fire_for_full_route_table(self) -> None:
        """No warning when a full route: table (with default) is used."""
        fsm = self._prompt_fsm(with_route=True)
        errors = _validate_partial_route_dead_end(fsm)
        assert errors == []

    def test_mr4_does_not_fire_for_non_llm_evaluator(self) -> None:
        """No warning when the state uses a deterministic exit_code evaluator."""
        fsm = FSMLoop(
            name="test-loop",
            initial="build",
            states={
                "build": make_state(
                    action="make",
                    action_type="shell",
                    evaluate=EvaluateConfig(type="exit_code"),
                    on_yes="done",
                    on_error="failed",
                ),
                "done": make_state(terminal=True),
                "failed": make_state(terminal=True),
            },
        )
        errors = _validate_partial_route_dead_end(fsm)
        assert errors == []

    def test_mr4_does_not_fire_when_on_yes_absent(self) -> None:
        """No warning when on_yes is not set at all (nothing to flag)."""
        fsm = FSMLoop(
            name="test-loop",
            initial="run",
            states={
                "run": make_state(action="Do something", action_type="prompt", on_no="run"),
                "done": make_state(terminal=True),
            },
        )
        errors = _validate_partial_route_dead_end(fsm)
        assert errors == []

    # --- suppression ---

    def test_mr4_suppressed_by_partial_route_ok(self) -> None:
        """partial_route_ok: true suppresses MR-4 entirely."""
        fsm = self._prompt_fsm(partial_route_ok=True)
        errors = _validate_partial_route_dead_end(fsm)
        assert errors == []

    # --- wiring ---

    def test_mr4_runs_via_validate_fsm(self) -> None:
        """validate_fsm() wires in MR-4 (end-to-end, not just direct call)."""
        fsm = self._prompt_fsm()
        errors = validate_fsm(fsm)
        mr4 = [
            e
            for e in errors
            if e.severity == ValidationSeverity.WARNING and "ENH-1917" in e.message
        ]
        assert len(mr4) == 1

    def test_partial_route_ok_recognized_as_top_level_key(self, tmp_path: Path) -> None:
        """A YAML with top-level partial_route_ok produces no Unknown-top-level warning."""
        loop_yaml = tmp_path / "loop.yaml"
        loop_yaml.write_text(
            "name: test-loop\n"
            "description: A loop where dead-ending on non-yes is intentional\n"
            "initial: run\n"
            "partial_route_ok: true\n"
            "states:\n"
            "  run:\n"
            "    action: /ll:do-thing\n"
            "    on_yes: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        _, warnings = load_and_validate(loop_yaml)
        unknown_warnings = [w for w in warnings if "Unknown top-level" in w.message]
        assert unknown_warnings == []


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


COUNTER_ACTION = 'N=$((N + 1)); printf "%d" "$N" > /tmp/counter.txt'


class TestZeroRetryCounterValidation:
    """ENH-1636: Zero-retry counter pattern lint for output_numeric evaluators."""

    def _fsm_with_counter(self, operator: str, target: float, action: str | None = None) -> FSMLoop:
        """Build a minimal FSM with a counter action and output_numeric evaluator."""
        return FSMLoop(
            name="test-zero-retry",
            initial="check",
            states={
                "check": make_state(
                    action=action if action is not None else COUNTER_ACTION,
                    evaluate=EvaluateConfig(
                        type="output_numeric", operator=operator, target=target
                    ),
                    on_yes="done",
                    on_no="check",
                ),
                "done": make_state(terminal=True),
            },
        )

    # --- Zero-retry warnings ---

    def test_warns_lt_target_1(self) -> None:
        """lt target=1 with counter action yields zero retries (1 < 1 is false)."""
        fsm = self._fsm_with_counter(operator="lt", target=1)
        errors = _validate_zero_retry_counter(fsm)
        assert len(errors) == 1
        assert errors[0].severity == ValidationSeverity.WARNING
        assert "target=1" in errors[0].message.lower()
        assert "states.check.evaluate" in (errors[0].path or "")

    def test_warns_lt_target_0(self) -> None:
        """lt target=0 with counter action yields zero retries (1 < 0 is false)."""
        fsm = self._fsm_with_counter(operator="lt", target=0)
        errors = _validate_zero_retry_counter(fsm)
        assert len(errors) == 1
        assert errors[0].severity == ValidationSeverity.WARNING

    def test_warns_le_target_0(self) -> None:
        """le target=0 with counter action yields zero retries (1 <= 0 is false)."""
        fsm = self._fsm_with_counter(operator="le", target=0)
        errors = _validate_zero_retry_counter(fsm)
        assert len(errors) == 1
        assert errors[0].severity == ValidationSeverity.WARNING

    def test_warns_eq_target_0(self) -> None:
        """eq target=0 with counter action yields zero retries (1 == 0 is false, counter never matches)."""
        fsm = self._fsm_with_counter(operator="eq", target=0)
        errors = _validate_zero_retry_counter(fsm)
        assert len(errors) == 1
        assert errors[0].severity == ValidationSeverity.WARNING

    # --- No warning (valid budget) ---

    def test_no_warn_lt_target_2(self) -> None:
        """lt target=2 with counter action allows one retry (1 < 2 is true)."""
        fsm = self._fsm_with_counter(operator="lt", target=2)
        errors = _validate_zero_retry_counter(fsm)
        assert errors == []

    def test_no_warn_lt_target_3(self) -> None:
        """lt target=3 with counter action allows two retries (1 < 3 is true)."""
        fsm = self._fsm_with_counter(operator="lt", target=3)
        errors = _validate_zero_retry_counter(fsm)
        assert errors == []

    def test_no_warn_gt_target_0(self) -> None:
        """gt target=0 with counter action allows retries (1 > 0 is true)."""
        fsm = self._fsm_with_counter(operator="gt", target=0)
        errors = _validate_zero_retry_counter(fsm)
        assert errors == []

    def test_no_warn_ge_target_1(self) -> None:
        """ge target=1 with counter action allows retries (1 >= 1 is true)."""
        fsm = self._fsm_with_counter(operator="ge", target=1)
        errors = _validate_zero_retry_counter(fsm)
        assert errors == []

    # --- Non-counter action ---

    def test_no_warn_non_counter_action(self) -> None:
        """Plain echo without increment is not a counter pattern."""
        fsm = self._fsm_with_counter(operator="lt", target=1, action='echo "hello" > /tmp/out.txt')
        errors = _validate_zero_retry_counter(fsm)
        assert errors == []

    # --- Missing evaluate / action ---

    def test_no_warn_no_evaluate(self) -> None:
        """State without evaluate block is skipped."""
        fsm = FSMLoop(
            name="test-no-eval",
            initial="check",
            states={
                "check": make_state(action=COUNTER_ACTION, on_yes="done"),
                "done": make_state(terminal=True),
            },
        )
        errors = _validate_zero_retry_counter(fsm)
        assert errors == []

    def test_no_warn_no_action(self) -> None:
        """State without action is skipped."""
        fsm = FSMLoop(
            name="test-no-action",
            initial="check",
            states={
                "check": make_state(
                    evaluate=EvaluateConfig(type="output_numeric", operator="lt", target=1),
                    on_yes="done",
                ),
                "done": make_state(terminal=True),
            },
        )
        errors = _validate_zero_retry_counter(fsm)
        assert errors == []

    def test_no_warn_non_output_numeric(self) -> None:
        """Counter action with exit_code evaluator is not flagged."""
        fsm = FSMLoop(
            name="test-exit-code",
            initial="check",
            states={
                "check": make_state(
                    action=COUNTER_ACTION,
                    evaluate=EvaluateConfig(type="exit_code"),
                    on_yes="done",
                ),
                "done": make_state(terminal=True),
            },
        )
        errors = _validate_zero_retry_counter(fsm)
        assert errors == []

    # --- Integration: wired into validate_fsm ---

    def test_integration_wired_into_validate_fsm(self) -> None:
        """validate_fsm() includes zero-retry counter warnings."""
        fsm = self._fsm_with_counter(operator="lt", target=1)
        errors = validate_fsm(fsm)
        warnings = [
            e for e in errors if "zero" in e.message.lower() or "retry" in e.message.lower()
        ]
        assert len(warnings) >= 1


class TestRetryableExitCodesValidation:
    """ENH-1678: retryable_exit_codes validation."""

    def test_retryable_exit_codes_without_on_error_is_error(self) -> None:
        """retryable_exit_codes requires on_error."""
        fsm = FSMLoop(
            name="test",
            initial="work",
            states={
                "work": StateConfig(
                    action="run.sh",
                    on_yes="done",
                    retryable_exit_codes=[1, 137],
                ),
                "done": StateConfig(terminal=True),
            },
        )
        errors = [e for e in validate_fsm(fsm) if e.severity == ValidationSeverity.ERROR]
        assert any("retryable_exit_codes" in e.message.lower() for e in errors)

    def test_retryable_exit_codes_with_on_error_passes(self) -> None:
        """retryable_exit_codes with on_error set produces no retryable_exit_codes errors."""
        fsm = FSMLoop(
            name="test",
            initial="work",
            states={
                "work": StateConfig(
                    action="run.sh",
                    on_error="work",
                    max_retries=2,
                    on_retry_exhausted="done",
                    retryable_exit_codes=[1, 137],
                ),
                "done": StateConfig(terminal=True),
            },
        )
        errors = [e for e in validate_fsm(fsm) if e.severity == ValidationSeverity.ERROR]
        rc_errors = [e for e in errors if "retryable_exit_codes" in e.message.lower()]
        assert rc_errors == []

    def test_non_positive_exit_code_is_rejected(self) -> None:
        """retryable_exit_codes entries must be positive integers."""
        fsm = FSMLoop(
            name="test",
            initial="work",
            states={
                "work": StateConfig(
                    action="run.sh",
                    on_error="work",
                    max_retries=1,
                    on_retry_exhausted="done",
                    retryable_exit_codes=[0, -1, 1],
                ),
                "done": StateConfig(terminal=True),
            },
        )
        errors = [e for e in validate_fsm(fsm) if e.severity == ValidationSeverity.ERROR]
        assert any(
            "positive" in e.message.lower() and "retryable_exit_codes" in e.message.lower()
            for e in errors
        )


class TestHarnessMultimodalEvaluatorBlindSpot:
    """ENH-1819: WARNING when harness loops use LLM multimodal eval as sole gate to terminal."""

    def _harness_fsm(self, **kwargs) -> FSMLoop:
        """Build a minimal harness-category FSM."""
        defaults: dict = {
            "name": "test-harness",
            "initial": "score",
            "category": "harness",
            "states": {
                "score": make_state(
                    action_type="prompt",
                    action="Read the screenshot screenshot.png and judge the output.",
                    evaluate=EvaluateConfig(type="output_contains", pattern="PASS"),
                    on_yes="done",
                ),
                "done": make_state(terminal=True),
            },
        }
        defaults.update(kwargs)
        return FSMLoop(**defaults)

    # --- positive control ---

    def test_fires_for_harness_multimodal_prompt_to_terminal(self) -> None:
        """WARNING fires when harness loop has multimodal prompt routing directly to terminal."""
        fsm = self._harness_fsm()
        errors = _validate_harness_multimodal_evaluator_blind_spot(fsm)
        assert len(errors) == 1, f"Expected one WARNING, got: {errors}"
        assert errors[0].severity == ValidationSeverity.WARNING
        assert "score" in str(errors[0])

    # --- negative controls ---

    def test_does_not_fire_for_non_harness_loop(self) -> None:
        """Does not fire when category is not harness."""
        fsm = self._harness_fsm(category="oracle")
        errors = _validate_harness_multimodal_evaluator_blind_spot(fsm)
        assert errors == [], f"Expected no warnings for non-harness, got: {errors}"

    def test_does_not_fire_when_on_yes_not_terminal(self) -> None:
        """Does not fire when on_yes routes to a non-terminal state."""
        fsm = self._harness_fsm(
            states={
                "score": make_state(
                    action_type="prompt",
                    action="Read the screenshot and evaluate.",
                    evaluate=EvaluateConfig(type="output_contains", pattern="PASS"),
                    on_yes="review",
                ),
                "review": make_state(action="echo check", on_yes="done"),
                "done": make_state(terminal=True),
            },
        )
        errors = _validate_harness_multimodal_evaluator_blind_spot(fsm)
        assert errors == [], f"Expected no warnings when on_yes not terminal, got: {errors}"

    def test_does_not_fire_when_shell_action_intervenes(self) -> None:
        """Does not fire when a shell-action state sits between prompt and terminal."""
        fsm = self._harness_fsm(
            states={
                "score": make_state(
                    action_type="prompt",
                    action="Read the screenshot and evaluate.",
                    evaluate=EvaluateConfig(type="output_contains", pattern="PASS"),
                    on_yes="smoke_test",
                ),
                "smoke_test": make_state(
                    action_type="shell",
                    action="pytest smoke_test.py",
                    on_yes="done",
                ),
                "done": make_state(terminal=True),
            },
        )
        errors = _validate_harness_multimodal_evaluator_blind_spot(fsm)
        assert errors == [], f"Expected no warnings with shell state intervening, got: {errors}"

    def test_does_not_fire_with_non_output_contains_evaluator(self) -> None:
        """Does not fire when evaluator is not output_contains."""
        fsm = self._harness_fsm(
            states={
                "score": make_state(
                    action_type="prompt",
                    action="Read the screenshot and evaluate.",
                    evaluate=EvaluateConfig(type="llm_structured"),
                    on_yes="done",
                ),
                "done": make_state(terminal=True),
            },
        )
        errors = _validate_harness_multimodal_evaluator_blind_spot(fsm)
        assert errors == [], f"Expected no warnings for non-output_contains, got: {errors}"

    def test_suppressed_by_meta_self_eval_ok(self) -> None:
        """meta_self_eval_ok: true suppresses the warning."""
        fsm = self._harness_fsm(meta_self_eval_ok=True)
        errors = _validate_harness_multimodal_evaluator_blind_spot(fsm)
        assert errors == [], f"meta_self_eval_ok should suppress warnings: {errors}"

    # --- integration ---

    def test_wired_into_validate_fsm(self) -> None:
        """validate_fsm() includes the multimodal evaluator warning."""
        fsm = self._harness_fsm()
        errors = validate_fsm(fsm)
        blind_spot_warnings = [
            e
            for e in errors
            if "multimodal" in e.message.lower() or "screenshot" in e.message.lower()
        ]
        assert len(blind_spot_warnings) == 1, (
            f"Expected one blind-spot warning in validate_fsm output, got: {blind_spot_warnings}"
        )


class TestValidateStateLearningGuard:
    """ENH-1741: _validate_state_action learning guard accepts targets_csv."""

    def _make_fsm(self, learning: LearningConfig) -> FSMLoop:
        return FSMLoop(
            name="test",
            initial="prove",
            states={
                "prove": StateConfig(
                    type="learning",
                    learning=learning,
                    on_yes="done",
                    on_blocked="done",
                ),
                "done": StateConfig(terminal=True),
            },
        )

    def test_targets_csv_only_passes_validation(self) -> None:
        """A learning state with only targets_csv set must not emit an ERROR."""
        state = StateConfig(
            type="learning",
            learning=LearningConfig(targets_csv="${context.targets}"),
            on_yes="done",
            on_blocked="done",
        )
        errors = _validate_state_action("prove", state)
        target_errors = [
            e
            for e in errors
            if "learning.targets" in e.path and e.severity == ValidationSeverity.ERROR
        ]
        assert target_errors == [], (
            f"targets_csv-only state should not produce an ERROR, got: {target_errors}"
        )

    def test_neither_targets_nor_targets_csv_emits_error(self) -> None:
        """A learning state with neither targets nor targets_csv must emit an ERROR."""
        state = StateConfig(
            type="learning",
            learning=LearningConfig(),  # empty targets, no targets_csv
            on_yes="done",
            on_blocked="done",
        )
        errors = _validate_state_action("prove", state)
        target_errors = [
            e
            for e in errors
            if "learning.targets" in e.path and e.severity == ValidationSeverity.ERROR
        ]
        assert len(target_errors) == 1, (
            f"Expected one ERROR for missing targets/targets_csv, got: {target_errors}"
        )


class TestRequiredInputsValidation:
    """Tests for _validate_input_key_without_guard (ENH-1898)."""

    def _make_fsm(self, input_key: str = "input", required_inputs: list | None = None) -> FSMLoop:
        return FSMLoop(
            name="test",
            initial="start",
            states={"start": make_state(terminal=True)},
            input_key=input_key,
            required_inputs=required_inputs or [],
        )

    def test_warning_fires_when_input_key_set_without_required_inputs(self) -> None:
        """WARNING emitted when input_key is custom but required_inputs is empty."""
        fsm = self._make_fsm(input_key="description", required_inputs=[])
        errors = _validate_input_key_without_guard(fsm)
        assert len(errors) == 1
        assert errors[0].severity == ValidationSeverity.WARNING
        assert "required_inputs" in errors[0].path
        assert "description" in errors[0].message

    def test_no_warning_when_required_inputs_declared(self) -> None:
        """No WARNING when required_inputs is declared alongside custom input_key."""
        fsm = self._make_fsm(input_key="description", required_inputs=["description"])
        errors = _validate_input_key_without_guard(fsm)
        assert errors == []

    def test_no_warning_for_default_input_key(self) -> None:
        """No WARNING when input_key is the default 'input' (not explicitly overridden)."""
        fsm = self._make_fsm(input_key="input", required_inputs=[])
        errors = _validate_input_key_without_guard(fsm)
        assert errors == []

    def test_warning_wired_into_validate_fsm(self) -> None:
        """_validate_input_key_without_guard is wired into validate_fsm."""
        fsm = self._make_fsm(input_key="topic", required_inputs=[])
        all_errors = validate_fsm(fsm)
        guard_warnings = [
            e
            for e in all_errors
            if e.severity == ValidationSeverity.WARNING and "required_inputs" in e.path
        ]
        assert len(guard_warnings) == 1

    def test_no_warning_when_required_inputs_wired_into_validate_fsm(self) -> None:
        """validate_fsm emits no guard WARNING when required_inputs is declared."""
        fsm = self._make_fsm(input_key="topic", required_inputs=["topic"])
        all_errors = validate_fsm(fsm)
        guard_warnings = [
            e
            for e in all_errors
            if e.severity == ValidationSeverity.WARNING and "required_inputs" in e.path
        ]
        assert guard_warnings == []


class TestValidateFragmentBindings:
    """Tests for _validate_fragment_bindings cross-validation."""

    def _make_fsm_with_fragment_state(
        self,
        fragment_name: str,
        bindings: dict,
        parameters: dict,
    ) -> FSMLoop:
        """Build an FSMLoop with one fragment state for validation testing."""
        from little_loops.fsm.schema import ParameterSpec

        parsed_params = {name: ParameterSpec.from_dict(spec) for name, spec in parameters.items()}
        return FSMLoop(
            name="test",
            initial="step",
            states={
                "step": StateConfig(
                    fragment_name=fragment_name,
                    fragment_bindings=bindings,
                    fragment_parameters=parsed_params,
                    action="echo ${param.key}",
                    action_type="shell",
                    next="done",
                ),
                "done": StateConfig(terminal=True),
            },
        )

    def test_valid_bindings_no_errors(self, tmp_path: Path) -> None:
        from little_loops.fsm.validation import _validate_fragment_bindings

        fsm = self._make_fsm_with_fragment_state(
            "counter",
            bindings={"counter_key": "my_counter"},
            parameters={"counter_key": {"type": "string", "required": True}},
        )
        errors = _validate_fragment_bindings(fsm, tmp_path)
        assert errors == []

    def test_unknown_binding_key_flagged(self, tmp_path: Path) -> None:
        from little_loops.fsm.validation import _validate_fragment_bindings

        fsm = self._make_fsm_with_fragment_state(
            "counter",
            bindings={"counter_key": "ok", "unknown_param": "oops"},
            parameters={"counter_key": {"type": "string", "required": True}},
        )
        errors = _validate_fragment_bindings(fsm, tmp_path)
        assert len(errors) == 1
        assert "unknown_param" in errors[0].message

    def test_missing_required_param_flagged(self, tmp_path: Path) -> None:
        from little_loops.fsm.validation import _validate_fragment_bindings

        fsm = self._make_fsm_with_fragment_state(
            "counter",
            bindings={},  # counter_key required but not bound
            parameters={"counter_key": {"type": "string", "required": True}},
        )
        errors = _validate_fragment_bindings(fsm, tmp_path)
        assert len(errors) == 1
        assert "counter_key" in errors[0].message

    def test_runner_injected_vars_not_flagged(self, tmp_path: Path) -> None:
        """run_dir, loop_name, started_at are runner-injected and should not be flagged."""
        from little_loops.fsm.validation import _validate_fragment_bindings

        fsm = self._make_fsm_with_fragment_state(
            "rubric_score",
            bindings={},  # run_dir NOT bound — but it's runner-injected
            parameters={"run_dir": {"type": "string", "required": True}},
        )
        errors = _validate_fragment_bindings(fsm, tmp_path)
        assert errors == []

    def test_type_mismatch_flagged(self, tmp_path: Path) -> None:
        from little_loops.fsm.validation import _validate_fragment_bindings

        fsm = self._make_fsm_with_fragment_state(
            "counter",
            bindings={"max_retries": "not_an_integer"},
            parameters={"max_retries": {"type": "integer", "required": True}},
        )
        errors = _validate_fragment_bindings(fsm, tmp_path)
        assert len(errors) == 1
        assert "max_retries" in errors[0].message

    def test_interpolated_value_skips_type_check(self, tmp_path: Path) -> None:
        """Values containing ${...} are skipped for type checking (resolved at runtime)."""
        from little_loops.fsm.validation import _validate_fragment_bindings

        fsm = self._make_fsm_with_fragment_state(
            "counter",
            bindings={"max_retries": "${context.some_value}"},
            parameters={"max_retries": {"type": "integer", "required": True}},
        )
        errors = _validate_fragment_bindings(fsm, tmp_path)
        assert errors == []

    def test_state_without_fragment_parameters_skipped(self, tmp_path: Path) -> None:
        """States with no fragment_parameters are silently skipped."""
        from little_loops.fsm.validation import _validate_fragment_bindings

        fsm = FSMLoop(
            name="test",
            initial="step",
            states={
                "step": StateConfig(action="echo hi", next="done"),
                "done": StateConfig(terminal=True),
            },
        )
        errors = _validate_fragment_bindings(fsm, tmp_path)
        assert errors == []
