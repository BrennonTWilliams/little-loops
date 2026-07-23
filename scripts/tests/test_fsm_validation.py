"""Tests for FSM validation logic.

Tests cover reachability analysis and routing validation, including
support for custom on_<verdict> routing via extra_routes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from little_loops.fsm.schema import (
    CircuitConfig,
    CostCeilingConfig,
    EvaluateConfig,
    FSMLoop,
    LearningConfig,
    ParameterSpec,
    PromptSizeGuardConfig,
    RepeatedFailureConfig,
    StateConfig,
    TargetFileSpec,
    ThrottleConfig,
)
from little_loops.fsm.validation import (
    ValidationSeverity,
    _validate_artifact_isolation,
    _validate_artifact_overwrite,
    _validate_bash_default_interpolation,
    _validate_capture_reachability,
    _validate_classify_route_default,
    _validate_evaluator,
    _validate_generator_fix_discipline,
    _validate_haiku_pinned_generator,
    _validate_harness_multimodal_evaluator_blind_spot,
    _validate_input_key_without_guard,
    _validate_llm_evidence_contract,
    _validate_meta_loop_evaluation,
    _validate_overescaped_shell,
    _validate_parameters,
    _validate_parse_swallow,
    _validate_partial_route_dead_end,
    _validate_policy_dimensions_scored,
    _validate_progress_paths_isolation,
    _validate_state_action,
    _validate_unsafe_context_interpolation,
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

    def test_worktree_without_loop_rejected(self) -> None:
        """worktree: without loop: produces an error (ENH-2609)."""
        fsm = FSMLoop(
            name="test",
            initial="bad",
            states={
                "bad": StateConfig(
                    action="echo hi",
                    worktree="some-branch",
                    on_yes="done",
                ),
                "done": StateConfig(terminal=True),
            },
        )
        errors = validate_fsm(fsm)
        assert any("'worktree' is only valid when 'loop' is set" in e.message for e in errors)

    def test_worktree_with_loop_accepted(self) -> None:
        """worktree: on a loop: state is valid (ENH-2609)."""
        fsm = FSMLoop(
            name="test",
            initial="ok",
            states={
                "ok": StateConfig(
                    loop="child",
                    worktree="${context.branch}",
                    on_yes="done",
                    on_no="done",
                ),
                "done": StateConfig(terminal=True),
            },
        )
        errors = validate_fsm(fsm)
        assert not any("'worktree'" in e.message for e in errors)

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


class TestCostCeilingValidation:
    """Tests for cost_ceiling_per_state / cost_warn_at validation (ENH-2477)."""

    def _make_fsm(self, ceiling: CostCeilingConfig | None) -> FSMLoop:
        kwargs: dict = {
            "name": "test",
            "initial": "work",
            "states": {
                "work": StateConfig(
                    action="run.sh",
                    on_yes="done",
                    cost_ceiling=ceiling,
                ),
                "done": StateConfig(terminal=True),
            },
        }
        return FSMLoop(**kwargs)

    def test_valid_ceiling_no_errors(self) -> None:
        fsm = self._make_fsm(CostCeilingConfig(cost_ceiling_per_state=1.0, cost_warn_at=0.5))
        errors = validate_fsm(fsm)
        ceiling_errors = [
            e
            for e in errors
            if "cost_ceiling" in e.message.lower() or "cost_warn_at" in e.message.lower()
        ]
        assert ceiling_errors == []

    def test_partial_ceiling_valid(self) -> None:
        """A ceiling with only one of the two fields set is valid."""
        fsm = self._make_fsm(CostCeilingConfig(cost_warn_at=0.5))
        errors = validate_fsm(fsm)
        ceiling_errors = [
            e
            for e in errors
            if "cost_ceiling" in e.message.lower() or "cost_warn_at" in e.message.lower()
        ]
        assert ceiling_errors == []

    def test_negative_ceiling_rejected(self) -> None:
        fsm = self._make_fsm(CostCeilingConfig(cost_ceiling_per_state=-1.0))
        errors = validate_fsm(fsm)
        assert any(
            "cost_ceiling" in e.message.lower() or "cost_ceiling_per_state" in e.message.lower()
            for e in errors
        )

    def test_negative_warn_at_rejected(self) -> None:
        fsm = self._make_fsm(CostCeilingConfig(cost_warn_at=-0.5))
        errors = validate_fsm(fsm)
        assert any("cost_warn_at" in e.message.lower() for e in errors)

    def test_warn_at_must_be_less_than_ceiling(self) -> None:
        fsm = self._make_fsm(CostCeilingConfig(cost_ceiling_per_state=0.5, cost_warn_at=1.0))
        errors = validate_fsm(fsm)
        # warn_at > ceiling is an inconsistent configuration.
        assert any(
            ("cost_warn_at" in e.message.lower() or "warn_at" in e.message.lower())
            and ("ceiling" in e.message.lower() or "cost_ceiling_per_state" in e.message.lower())
            for e in errors
        )

    def test_no_ceiling_means_no_validation_errors(self) -> None:
        fsm = self._make_fsm(None)
        errors = validate_fsm(fsm)
        ceiling_errors = [
            e
            for e in errors
            if "cost_ceiling" in e.message.lower() or "cost_warn_at" in e.message.lower()
        ]
        assert ceiling_errors == []


class TestPromptSizeGuardValidation:
    """Tests for prompt_size_guard validation (ENH-2486)."""

    def _make_fsm(self, guard: PromptSizeGuardConfig) -> FSMLoop:
        return FSMLoop(
            name="test",
            initial="work",
            states={
                "work": StateConfig(action="run.sh", next="done"),
                "done": StateConfig(terminal=True),
            },
            prompt_size_guard=guard,
        )

    def test_default_guard_no_errors(self) -> None:
        errors = validate_fsm(self._make_fsm(PromptSizeGuardConfig()))
        assert [e for e in errors if "prompt_size_guard" in e.path] == []

    def test_zero_warn_chars_valid(self) -> None:
        """warn_chars=0 disables the guard and is valid."""
        errors = validate_fsm(self._make_fsm(PromptSizeGuardConfig(warn_chars=0)))
        assert [e for e in errors if "prompt_size_guard" in e.path] == []

    def test_negative_warn_chars_rejected(self) -> None:
        errors = validate_fsm(self._make_fsm(PromptSizeGuardConfig(warn_chars=-1)))
        assert any("prompt_size_guard.warn_chars" in e.path and ">= 0" in e.message for e in errors)


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

    def test_recurrent_window_valid_value_accepted(self) -> None:
        """ENH-2245: recurrent_window >= 2 produces no validation errors."""
        fsm = self._make_fsm(
            RepeatedFailureConfig(window=3, on_repeated_failure="abort", recurrent_window=5)
        )
        errors = [e for e in validate_fsm(fsm) if e.severity == ValidationSeverity.ERROR]
        circuit_errors = [e for e in errors if "recurrent_window" in (e.path or "")]
        assert circuit_errors == []

    def test_recurrent_window_below_minimum_rejected(self) -> None:
        """ENH-2245: recurrent_window=1 is rejected (minimum is 2)."""
        fsm = self._make_fsm(
            RepeatedFailureConfig(window=3, on_repeated_failure="abort", recurrent_window=1)
        )
        errors = validate_fsm(fsm)
        assert any("recurrent_window" in (e.path or "") and ">= 2" in e.message for e in errors)

    def test_recurrent_window_none_accepted(self) -> None:
        """ENH-2245: recurrent_window=None (default/disabled) produces no errors."""
        fsm = self._make_fsm(
            RepeatedFailureConfig(window=3, on_repeated_failure="abort", recurrent_window=None)
        )
        errors = [e for e in validate_fsm(fsm) if e.severity == ValidationSeverity.ERROR]
        circuit_errors = [e for e in errors if "recurrent_window" in (e.path or "")]
        assert circuit_errors == []

    def test_recurrent_window_in_yaml_no_unknown_key_warning(self, tmp_path: Path) -> None:
        """ENH-2245: recurrent_window in YAML produces no unknown-key warnings."""
        loop_yaml = self._write_yaml(
            tmp_path,
            (
                "name: test-loop\n"
                "description: A loop with recurrent_window\n"
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
                "    recurrent_window: 5\n"
            ),
        )
        _, warnings = load_and_validate(loop_yaml)
        unknown_warnings = [
            w for w in warnings if "Unknown" in w.message or "additional" in w.message.lower()
        ]
        assert unknown_warnings == []


class TestVisibilityValidation:
    """Visibility tier field: recognized top-level key + value validation."""

    def _write_yaml(self, tmp_path: Path, body: str) -> Path:
        p = tmp_path / "loop.yaml"
        p.write_text(body)
        return p

    _BASE = (
        "name: vis-loop\n"
        "description: t\n"
        "initial: work\n"
        "states:\n"
        "  work:\n"
        "    action: run.sh\n"
        "    on_yes: done\n"
        "  done:\n"
        "    terminal: true\n"
    )

    @pytest.mark.parametrize("vis", ["public", "internal", "example"])
    def test_valid_visibility_no_warning(self, tmp_path: Path, vis: str) -> None:
        """A recognized visibility value produces no unknown-key or value warning."""
        loop_yaml = self._write_yaml(tmp_path, self._BASE + f"visibility: {vis}\n")
        fsm, warnings = load_and_validate(loop_yaml)
        assert fsm.visibility == vis
        assert not any(
            "Unknown top-level" in w.message or "Invalid visibility" in w.message for w in warnings
        )

    def test_invalid_visibility_warns(self, tmp_path: Path) -> None:
        """An out-of-range visibility value yields a WARNING, not an error."""
        loop_yaml = self._write_yaml(tmp_path, self._BASE + "visibility: secret\n")
        _, warnings = load_and_validate(loop_yaml)
        vis_warnings = [w for w in warnings if "Invalid visibility" in w.message]
        assert len(vis_warnings) == 1
        assert vis_warnings[0].severity == ValidationSeverity.WARNING
        assert vis_warnings[0].path == "visibility"

    def test_visibility_roundtrips_through_serialization(self) -> None:
        """visibility survives to_dict/from_dict; default 'public' is omitted."""
        fsm = FSMLoop(
            name="t",
            initial="check",
            description="d",
            states={"check": make_state(terminal=True)},
            visibility="internal",
        )
        assert FSMLoop.from_dict(fsm.to_dict()).visibility == "internal"
        # Default value is not serialized.
        default = FSMLoop(name="t", initial="check", states={"check": make_state(terminal=True)})
        assert "visibility" not in default.to_dict()


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

    def test_mr1_passes_when_score_stall_evaluator_present(self) -> None:
        """MR-1 does not fire when at least one score_stall evaluator is present (ENH-2428)."""
        fsm = self._meta_fsm(
            states={
                "check": make_state(
                    action="run.sh",
                    evaluate=EvaluateConfig(type="score_stall"),
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


class TestModelStateValidation:
    """ENH-2073: model: override validation — WARNING for non-prompt states."""

    def test_model_on_shell_state_emits_warning(self) -> None:
        """model: on a shell state emits a validation WARNING."""
        fsm = FSMLoop(
            name="test-loop",
            initial="work",
            states={
                "work": StateConfig(
                    action="echo hi",
                    action_type="shell",
                    model="claude-haiku-4-5-20251001",
                    next="done",
                ),
                "done": make_state(terminal=True),
            },
        )
        errors = _validate_state_action("work", fsm.states["work"])
        warnings = [e for e in errors if e.severity == ValidationSeverity.WARNING]
        assert any("model" in w.message and "ignored" in w.message for w in warnings)

    def test_model_on_prompt_state_no_warning(self) -> None:
        """model: on a prompt state does not emit a warning."""
        fsm = FSMLoop(
            name="test-loop",
            initial="work",
            states={
                "work": StateConfig(
                    action="/ll:test",
                    action_type="prompt",
                    model="claude-haiku-4-5-20251001",
                    next="done",
                ),
                "done": make_state(terminal=True),
            },
        )
        errors = _validate_state_action("work", fsm.states["work"])
        model_warnings = [
            e for e in errors if e.severity == ValidationSeverity.WARNING and "model" in e.message
        ]
        assert model_warnings == []

    def test_model_on_mcp_tool_state_emits_warning(self) -> None:
        """model: on an mcp_tool state emits a validation WARNING."""
        state = StateConfig(
            action="server/tool",
            action_type="mcp_tool",
            model="claude-opus-4-8",
            next="done",
        )
        errors = _validate_state_action("check", state)
        warnings = [e for e in errors if e.severity == ValidationSeverity.WARNING]
        assert any("model" in w.message and "ignored" in w.message for w in warnings)

    def test_model_on_shell_state_with_llm_structured_evaluate_no_warning(self) -> None:
        """ENH-2713: model: on a shell state IS used when paired with an
        llm_structured evaluate block, so the "ignored" WARNING must not fire."""
        state = StateConfig(
            action="run.sh",
            action_type="shell",
            model="claude-haiku-4-5-20251001",
            evaluate=EvaluateConfig(type="llm_structured"),
            on_yes="done",
            on_no="work",
        )
        errors = _validate_state_action("work", state)
        model_warnings = [
            e for e in errors if e.severity == ValidationSeverity.WARNING and "model" in e.message
        ]
        assert model_warnings == []


class TestHaikuPinnedGenerator:
    """ENH-2713: haiku-pinned generator states get a WARN — no MR-1 backstop."""

    def _fsm(self, work_state: StateConfig, *, haiku_generator_ok: bool = False) -> FSMLoop:
        return FSMLoop(
            name="test-loop",
            initial="work",
            states={
                "work": work_state,
                "done": make_state(terminal=True),
            },
            haiku_generator_ok=haiku_generator_ok,
        )

    def test_fires_for_haiku_pinned_generator_state(self) -> None:
        """A prompt-action generator state (graded by a non-LLM evaluator, so its
        content is never quality-checked) pinned to haiku is flagged."""
        fsm = self._fsm(
            make_state(
                action="/ll:write-summary",
                action_type="prompt",
                model="claude-haiku-4-5-20251001",
                evaluate=EvaluateConfig(type="exit_code"),
                on_yes="done",
                on_no="work",
            )
        )
        errors = _validate_haiku_pinned_generator(fsm)
        assert len(errors) == 1
        assert errors[0].severity == ValidationSeverity.WARNING
        assert errors[0].path == "states.work.model"

    def test_does_not_fire_for_haiku_pinned_verdict_state(self) -> None:
        """An llm_structured verdict state pinned to haiku is not flagged."""
        fsm = self._fsm(
            make_state(
                action="run.sh",
                action_type="shell",
                model="claude-haiku-4-5-20251001",
                evaluate=EvaluateConfig(type="llm_structured"),
                on_yes="done",
                on_no="work",
            )
        )
        errors = _validate_haiku_pinned_generator(fsm)
        assert errors == []

    def test_does_not_fire_for_non_haiku_model(self) -> None:
        """A generator state pinned to a non-haiku model is not flagged."""
        fsm = self._fsm(
            make_state(
                action="/ll:write-summary",
                action_type="prompt",
                model="claude-opus-4-8",
                next="done",
            )
        )
        errors = _validate_haiku_pinned_generator(fsm)
        assert errors == []

    def test_does_not_fire_without_model(self) -> None:
        """A generator state with no model: override is not flagged."""
        fsm = self._fsm(make_state(action="/ll:write-summary", action_type="prompt", next="done"))
        errors = _validate_haiku_pinned_generator(fsm)
        assert errors == []

    def test_suppressed_by_haiku_generator_ok(self) -> None:
        """haiku_generator_ok: true suppresses the rule."""
        fsm = self._fsm(
            make_state(
                action="/ll:write-summary",
                action_type="prompt",
                model="claude-haiku-4-5-20251001",
                evaluate=EvaluateConfig(type="exit_code"),
                on_yes="done",
                on_no="work",
            ),
            haiku_generator_ok=True,
        )
        errors = _validate_haiku_pinned_generator(fsm)
        assert errors == []

    def test_wired_into_validate_fsm(self) -> None:
        """validate_fsm() includes the haiku-pinned-generator WARN."""
        fsm = self._fsm(
            make_state(
                action="/ll:write-summary",
                action_type="prompt",
                model="claude-haiku-4-5-20251001",
                evaluate=EvaluateConfig(type="exit_code"),
                on_yes="done",
                on_no="work",
            )
        )
        errors = validate_fsm(fsm)
        matches = [
            e
            for e in errors
            if e.severity == ValidationSeverity.WARNING and "(ENH-2713)" in e.message
        ]
        assert len(matches) == 1

    def test_haiku_generator_ok_recognized_as_top_level_key(self, tmp_path: Path) -> None:
        """A YAML with top-level haiku_generator_ok produces no Unknown-top-level warning."""
        loop_yaml = tmp_path / "loop.yaml"
        loop_yaml.write_text(
            "name: test-loop\n"
            "description: A loop that intentionally pins haiku on a generator state\n"
            "initial: work\n"
            "haiku_generator_ok: true\n"
            "states:\n"
            "  work:\n"
            "    action: /ll:write-summary\n"
            "    action_type: prompt\n"
            "    model: claude-haiku-4-5-20251001\n"
            "    evaluate:\n"
            "      type: exit_code\n"
            "    on_yes: done\n"
            "    on_no: work\n"
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

    def test_input_hash_in_runner_injected(self, tmp_path: Path) -> None:
        """input_hash is runner-injected and should not be flagged as missing binding."""
        from little_loops.fsm.validation import _validate_fragment_bindings

        fsm = self._make_fsm_with_fragment_state(
            "rubric_score",
            bindings={},  # input_hash NOT bound — but it's runner-injected
            parameters={"input_hash": {"type": "string", "required": True}},
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


class TestArtifactVersioning:
    """MR-5 (ENH-1957): harness loops that overwrite artifacts without versioning."""

    def _iterative_harness_fsm(
        self,
        *,
        artifact_versioning: bool = False,
        artifact_versioning_ok: bool = False,
        category: str = "harness",
        with_loop: bool = False,
        non_iterative: bool = False,
    ) -> FSMLoop:
        """Build a minimal FSM for MR-5 testing.

        Default: iterative generate→evaluate→generate cycle with a flat artifact write.
        """
        if non_iterative:
            # Linear: no loop-back; generate → evaluate → done
            states = {
                "generate": make_state(
                    action="echo 'artifact' > ${context.run_dir}/output.svg",
                    action_type="shell",
                    next="evaluate",
                ),
                "evaluate": make_state(
                    action="Rate this output",
                    action_type="prompt",
                    evaluate=EvaluateConfig(type="exit_code"),
                    on_yes="done",
                    on_no="done",
                ),
                "done": make_state(terminal=True),
            }
        elif with_loop:
            # Uses sub-loop delegation (no direct artifact writes)
            states = {
                "generate": make_state(
                    action="oracles/generator-evaluator",
                    action_type="loop",
                    on_yes="done",
                    on_no="generate",
                ),
                "done": make_state(terminal=True),
            }
        else:
            # Iterative: generate → evaluate → [generate]
            states = {
                "generate": make_state(
                    action="echo 'artifact' > ${context.run_dir}/output.svg",
                    action_type="shell",
                    next="evaluate",
                ),
                "evaluate": make_state(
                    action="Rate this output",
                    action_type="prompt",
                    evaluate=EvaluateConfig(type="exit_code"),
                    on_yes="done",
                    on_no="generate",
                ),
                "done": make_state(terminal=True),
            }
        return FSMLoop(
            name="test-loop",
            initial="generate",
            states=states,
            category=category,
            artifact_versioning=artifact_versioning,
            artifact_versioning_ok=artifact_versioning_ok,
        )

    # --- MR-5 fires for iterative harness loops ---

    def test_mr5_fires_for_iterative_harness_with_flat_artifact(self) -> None:
        """MR-5 WARNING when harness loop overwrites artifact without versioning."""
        fsm = self._iterative_harness_fsm()
        errors = _validate_artifact_overwrite(fsm)
        assert len(errors) >= 1
        assert errors[0].severity == ValidationSeverity.WARNING

    # --- Suppression flags ---

    def test_mr5_suppressed_by_artifact_versioning_true(self) -> None:
        """MR-5 does NOT fire when artifact_versioning: true."""
        fsm = self._iterative_harness_fsm(artifact_versioning=True)
        errors = _validate_artifact_overwrite(fsm)
        assert errors == []

    def test_mr5_suppressed_by_artifact_versioning_ok_true(self) -> None:
        """MR-5 does NOT fire when artifact_versioning_ok: true."""
        fsm = self._iterative_harness_fsm(artifact_versioning_ok=True)
        errors = _validate_artifact_overwrite(fsm)
        assert errors == []

    # --- Non-iterative loops are exempt ---

    def test_mr5_does_not_fire_for_non_iterative_harness(self) -> None:
        """MR-5 does NOT fire for linear (non-iterative) harness loops."""
        fsm = self._iterative_harness_fsm(non_iterative=True)
        errors = _validate_artifact_overwrite(fsm)
        assert errors == []

    # --- Non-harness loops are exempt ---

    def test_mr5_does_not_fire_for_non_harness_category(self) -> None:
        """MR-5 does NOT fire for non-harness category loops."""
        fsm = self._iterative_harness_fsm(category="data")
        errors = _validate_artifact_overwrite(fsm)
        assert errors == []

    # --- Sub-loop delegation is exempt ---

    def test_mr5_does_not_fire_for_loop_delegation(self) -> None:
        """MR-5 does NOT fire when artifact work is delegated to a sub-loop."""
        fsm = self._iterative_harness_fsm(with_loop=True)
        errors = _validate_artifact_overwrite(fsm)
        assert errors == []

    # --- End-to-end: validate_fsm() wiring ---

    def test_mr5_wired_into_validate_fsm(self) -> None:
        """validate_fsm() includes MR-5 warnings for iterative harness loops."""
        fsm = self._iterative_harness_fsm()
        errors = validate_fsm(fsm)
        mr5 = [
            e
            for e in errors
            if e.severity == ValidationSeverity.WARNING
            and "artifact" in e.message.lower()
            and "version" in e.message.lower()
        ]
        assert len(mr5) == 1

    # --- Top-level key recognition ---

    def test_artifact_versioning_recognized_as_top_level_key(self, tmp_path: Path) -> None:
        """YAML with top-level artifact_versioning produces no Unknown-top-level warning."""
        loop_yaml = tmp_path / "loop.yaml"
        loop_yaml.write_text(
            "name: test-loop\n"
            "description: A loop that snapshots artifacts per iteration\n"
            "initial: work\n"
            "artifact_versioning: true\n"
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

    def test_artifact_versioning_ok_recognized_as_top_level_key(self, tmp_path: Path) -> None:
        """YAML with top-level artifact_versioning_ok produces no Unknown-top-level warning."""
        loop_yaml = tmp_path / "loop.yaml"
        loop_yaml.write_text(
            "name: test-loop\n"
            "description: A loop that intentionally overwrites artifacts\n"
            "initial: work\n"
            "artifact_versioning_ok: true\n"
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


class TestGeneratorFixDiscipline:
    """MR-6 (ENH-2079): meta-loops should not hand-patch LLM-generator artifacts."""

    def _mr6_fsm(
        self,
        *,
        generator_fix_ok: bool = False,
        same_path: bool = True,
        with_marker: bool = True,
        is_meta_loop: bool = True,
    ) -> FSMLoop:
        """Build a minimal FSM for MR-6 testing.

        Default: meta-loop with overlapping shell + generator paths (should trigger MR-6).
        """
        gen_path = "${context.run_dir}/output.yaml"
        shell_path = gen_path if same_path else "${context.run_dir}/other.txt"

        if with_marker:
            gen_action = f"Use yaml_state_editor to generate {gen_path} with the proposed changes."
        else:
            gen_action = f"Write the result to {gen_path} with the proposed changes."

        states = {
            "generate": make_state(
                action=gen_action,
                action_type="prompt",
                next="patch",
            ),
            "patch": make_state(
                action=f"echo patched > {shell_path}",
                action_type="shell",
                next="done",
            ),
            "done": make_state(terminal=True),
        }
        imports = ["lib/benchmark.yaml"] if is_meta_loop and not with_marker else []
        return FSMLoop(
            name="test-mr6",
            initial="generate",
            states=states,
            generator_fix_ok=generator_fix_ok,
            imports=imports,
        )

    def test_mr6_fires_when_shell_and_generator_write_same_path(self) -> None:
        """MR-6 WARNING fires when a shell state patches the same path as a generator state."""
        fsm = self._mr6_fsm()
        errors = _validate_generator_fix_discipline(fsm)
        assert len(errors) == 1
        assert errors[0].severity == ValidationSeverity.WARNING
        assert "ENH-2079" in errors[0].message

    def test_mr6_does_not_fire_when_no_path_overlap(self) -> None:
        """MR-6 does NOT fire when shell and generator states write to different paths."""
        fsm = self._mr6_fsm(same_path=False)
        errors = _validate_generator_fix_discipline(fsm)
        assert errors == []

    def test_mr6_does_not_fire_without_generator_marker(self) -> None:
        """MR-6 does NOT fire when the prompt state has no yaml_state_editor marker."""
        fsm = self._mr6_fsm(with_marker=False, is_meta_loop=True)
        errors = _validate_generator_fix_discipline(fsm)
        assert errors == []

    def test_mr6_suppressed_by_generator_fix_ok(self) -> None:
        """MR-6 does NOT fire when generator_fix_ok: true is set."""
        fsm = self._mr6_fsm(generator_fix_ok=True)
        errors = _validate_generator_fix_discipline(fsm)
        assert errors == []

    def test_mr6_wired_into_validate_fsm(self) -> None:
        """validate_fsm() includes MR-6 warnings for hand-patching anti-pattern."""
        fsm = self._mr6_fsm()
        errors = validate_fsm(fsm)
        mr6 = [
            e
            for e in errors
            if e.severity == ValidationSeverity.WARNING and "ENH-2079" in e.message
        ]
        assert len(mr6) == 1


class TestBashDefaultInterpolation:
    """MR-7 (ENH-2348): unescaped ${ns.path:-default} bash-default interpolation lint."""

    def _simple_fsm(self, action: str, *, bash_default_ok: bool = False) -> FSMLoop:
        return FSMLoop(
            name="test-loop",
            initial="work",
            states={
                "work": make_state(action=action, on_yes="done", on_no="work"),
                "done": make_state(terminal=True),
            },
            bash_default_ok=bash_default_ok,
        )

    def test_mr7_fires_for_unescaped_bash_default(self) -> None:
        """MR-7 ERROR fires when an action contains ${ns.path:-default}."""
        fsm = self._simple_fsm("echo ${context.order:-queue}")
        errors = _validate_bash_default_interpolation(fsm)
        assert len(errors) == 1
        assert errors[0].severity == ValidationSeverity.ERROR
        assert "${context.order:-queue}" in errors[0].message
        assert errors[0].path == "states.work.action"

    def test_mr7_does_not_fire_for_engine_default(self) -> None:
        """MR-7 does not fire for ${ns.path:default=value} (engine-native form)."""
        fsm = self._simple_fsm("echo ${context.order:default=queue}")
        errors = _validate_bash_default_interpolation(fsm)
        assert errors == []

    def test_mr7_does_not_fire_for_escaped_bash_default(self) -> None:
        """MR-7 does not fire for $${VAR:-value} (escaped, handled by shell)."""
        fsm = self._simple_fsm("echo $${DEPTH:-0}")
        errors = _validate_bash_default_interpolation(fsm)
        assert errors == []

    def test_mr7_suppressed_by_bash_default_ok(self) -> None:
        """bash_default_ok: true suppresses MR-7."""
        fsm = self._simple_fsm("echo ${context.order:-queue}", bash_default_ok=True)
        errors = _validate_bash_default_interpolation(fsm)
        assert errors == []

    def test_mr7_wired_into_validate_fsm(self) -> None:
        """validate_fsm() includes MR-7 errors for bash-default interpolation."""
        fsm = self._simple_fsm("echo ${context.order:-queue}")
        errors = validate_fsm(fsm)
        mr7 = [
            e for e in errors if e.severity == ValidationSeverity.ERROR and "ENH-2348" in e.message
        ]
        assert len(mr7) == 1

    def test_bash_default_ok_recognized_as_top_level_key(self, tmp_path: Path) -> None:
        """A YAML with top-level bash_default_ok produces no Unknown-top-level warning."""
        loop_yaml = tmp_path / "loop.yaml"
        loop_yaml.write_text(
            "name: test-loop\n"
            "description: A loop that intentionally uses bash default syntax\n"
            "initial: work\n"
            "bash_default_ok: true\n"
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


class TestOverescapedShell:
    """MR-9: over-escaped shell `$$` that expands to the PID at `bash -c` time."""

    def _simple_fsm(
        self,
        action: str,
        *,
        action_type: str | None = "shell",
        shell_pid_ok: bool = False,
    ) -> FSMLoop:
        return FSMLoop(
            name="test-loop",
            initial="work",
            states={
                "work": make_state(
                    action=action, action_type=action_type, on_yes="done", on_no="work"
                ),
                "done": make_state(terminal=True),
            },
            shell_pid_ok=shell_pid_ok,
        )

    def test_mr9_fires_for_overescaped_command_substitution(self) -> None:
        """MR-9 ERROR fires for $$( command substitution."""
        fsm = self._simple_fsm('echo "$$(pwd)"')
        errors = _validate_overescaped_shell(fsm)
        assert len(errors) == 1
        assert errors[0].severity == ValidationSeverity.ERROR
        assert errors[0].path == "states.work.action"
        assert "$$(" in errors[0].message

    def test_mr9_fires_for_overescaped_variable(self) -> None:
        """MR-9 ERROR fires for a bare $$VAR reference."""
        fsm = self._simple_fsm('echo "$$DIR"')
        errors = _validate_overescaped_shell(fsm)
        assert len(errors) == 1
        assert errors[0].severity == ValidationSeverity.ERROR

    def test_mr9_counts_each_occurrence(self) -> None:
        """The real init bug ($$(pwd)/$$DIR) yields two findings."""
        fsm = self._simple_fsm('echo "$$(pwd)/$$DIR"')
        errors = _validate_overescaped_shell(fsm)
        assert len(errors) == 2

    def test_mr9_does_not_fire_for_correct_single_dollar(self) -> None:
        """MR-9 does not fire for the correct $(pwd)/$DIR form."""
        fsm = self._simple_fsm('echo "$(pwd)/$DIR"')
        errors = _validate_overescaped_shell(fsm)
        assert errors == []

    def test_mr9_does_not_fire_for_legit_brace_escape(self) -> None:
        """MR-9 does not fire for the legit $${VAR} / $${VAR:-x} brace escape."""
        fsm = self._simple_fsm('[ -z "$${VISION_API_KEY:-}" ] && echo "$${HOME}"')
        errors = _validate_overescaped_shell(fsm)
        assert errors == []

    def test_mr9_does_not_fire_for_standalone_pid(self) -> None:
        """MR-9 does not fire for a standalone PID `$$` (tmp.$$ / "$$ ")."""
        fsm = self._simple_fsm('echo "tmp.$$"; echo "pid=$$ "')
        errors = _validate_overescaped_shell(fsm)
        assert errors == []

    def test_mr9_ignores_prompt_actions(self) -> None:
        """A $$VAR in a prompt action is inert text and is not flagged."""
        fsm = self._simple_fsm("Summarize $$DIR for the user", action_type="prompt")
        errors = _validate_overescaped_shell(fsm)
        assert errors == []

    def test_mr9_suppressed_by_shell_pid_ok(self) -> None:
        """shell_pid_ok: true suppresses MR-9."""
        fsm = self._simple_fsm('echo "$$(pwd)"', shell_pid_ok=True)
        errors = _validate_overescaped_shell(fsm)
        assert errors == []

    def test_mr9_wired_into_validate_fsm(self) -> None:
        """validate_fsm() includes MR-9 errors for over-escaped shell $$."""
        fsm = self._simple_fsm('echo "$$(pwd)"')
        errors = validate_fsm(fsm)
        mr9 = [
            e for e in errors if e.severity == ValidationSeverity.ERROR and "(MR-9)" in e.message
        ]
        assert len(mr9) == 1

    def test_shell_pid_ok_recognized_as_top_level_key(self, tmp_path: Path) -> None:
        """A YAML with top-level shell_pid_ok produces no Unknown-top-level warning."""
        loop_yaml = tmp_path / "loop.yaml"
        loop_yaml.write_text(
            "name: test-loop\n"
            "description: A loop that intentionally embeds a literal PID via $$\n"
            "initial: work\n"
            "shell_pid_ok: true\n"
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


class TestUnsafeContextInterpolation:
    """MR-11 (BUG-2622): user-controlled ${context.*} pasted raw into a shell body."""

    def _simple_fsm(
        self,
        action: str,
        *,
        action_type: str | None = "shell",
        unsafe_context_interpolation_ok: bool = False,
    ) -> FSMLoop:
        return FSMLoop(
            name="test-loop",
            initial="work",
            states={
                "work": make_state(
                    action=action, action_type=action_type, on_yes="done", on_no="work"
                ),
                "done": make_state(terminal=True),
            },
            unsafe_context_interpolation_ok=unsafe_context_interpolation_ok,
        )

    def test_mr11_fires_for_double_quoted_token_position(self) -> None:
        """MR-11 WARNING fires for [ -z "${context.input}" ] (the BUG-2622 repro)."""
        fsm = self._simple_fsm('if [ -z "${context.input}" ]; then exit 1; fi')
        errors = _validate_unsafe_context_interpolation(fsm)
        assert len(errors) == 1
        assert errors[0].severity == ValidationSeverity.WARNING
        assert errors[0].path == "states.work.action"
        assert "${context.input}" in errors[0].message

    def test_mr11_fires_for_bare_unquoted_token(self) -> None:
        """MR-11 fires for a bare unquoted ${context.goal} token position."""
        fsm = self._simple_fsm("echo ${context.goal}")
        errors = _validate_unsafe_context_interpolation(fsm)
        assert len(errors) == 1

    def test_mr11_fires_for_each_user_controlled_var_name(self) -> None:
        """MR-11 recognizes input/goal/description/task/prompt/query/topic."""
        for var in ("input", "goal", "description", "task", "prompt", "query", "topic"):
            fsm = self._simple_fsm(f'echo "${{context.{var}}}"')
            errors = _validate_unsafe_context_interpolation(fsm)
            assert len(errors) == 1, f"expected a finding for context.{var}"

    def test_mr11_does_not_fire_for_other_context_vars(self) -> None:
        """MR-11 does not flag non-user-controlled context vars like run_dir."""
        fsm = self._simple_fsm('echo "${context.run_dir}"')
        errors = _validate_unsafe_context_interpolation(fsm)
        assert errors == []

    def test_mr11_does_not_fire_for_epic_context_var(self) -> None:
        """MR-11 does not flag context.epic (ENH-2660): ``epic`` is outside the
        user-controlled regex set, so rn-implement's --epic branch can interpolate
        ``${context.epic}`` bare without needing unsafe_context_interpolation_ok.
        Locks the regex-bounded scope against a future "tighten MR-11" change."""
        fsm = self._simple_fsm('EPIC="${context.epic}"; echo "$EPIC"')
        errors = _validate_unsafe_context_interpolation(fsm)
        assert errors == []

    def test_mr11_does_not_fire_for_single_quoted_position(self) -> None:
        """MR-11 does not fire when the placeholder sits inside single quotes."""
        fsm = self._simple_fsm("printf '%s' '${context.input}'")
        errors = _validate_unsafe_context_interpolation(fsm)
        assert errors == []

    def test_mr11_does_not_fire_inside_quoted_heredoc(self) -> None:
        """MR-11 does not fire for a value written through a quoted heredoc."""
        fsm = self._simple_fsm(
            "cat > \"${context.run_dir}/in.txt\" <<'LL_EOF'\n${context.input}\nLL_EOF\n"
        )
        errors = _validate_unsafe_context_interpolation(fsm)
        assert errors == []

    def test_mr11_does_not_fire_for_shell_suffix(self) -> None:
        """MR-11 does not fire when the placeholder already uses :shell."""
        fsm = self._simple_fsm("INPUT=${context.input:shell}")
        errors = _validate_unsafe_context_interpolation(fsm)
        assert errors == []

    def test_mr11_does_not_fire_in_comment(self) -> None:
        """MR-11 does not fire for a placeholder mentioned only in a comment."""
        fsm = self._simple_fsm("# Never test ${context.input} as a bare token.\necho ok")
        errors = _validate_unsafe_context_interpolation(fsm)
        assert errors == []

    def test_mr11_ignores_prompt_actions(self) -> None:
        """A raw ${context.input} in a prompt action is safe (LLM payload, not bash)."""
        fsm = self._simple_fsm('Describe: "${context.input}"', action_type="prompt")
        errors = _validate_unsafe_context_interpolation(fsm)
        assert errors == []

    def test_mr11_ignores_slash_command_actions(self) -> None:
        """A raw ${context.input} in a slash-command body is not shell-parsed."""
        fsm = self._simple_fsm('/ll:refine-issue "${context.input}"')
        errors = _validate_unsafe_context_interpolation(fsm)
        assert errors == []

    def test_mr11_suppressed_by_flag(self) -> None:
        """unsafe_context_interpolation_ok: true suppresses MR-11."""
        fsm = self._simple_fsm('echo "${context.input}"', unsafe_context_interpolation_ok=True)
        errors = _validate_unsafe_context_interpolation(fsm)
        assert errors == []

    def test_mr11_wired_into_validate_fsm(self) -> None:
        """validate_fsm() includes MR-11 warnings for unsafe raw context interpolation."""
        fsm = self._simple_fsm('echo "${context.input}"')
        errors = validate_fsm(fsm)
        mr11 = [
            e for e in errors if e.severity == ValidationSeverity.WARNING and "(MR-11)" in e.message
        ]
        assert len(mr11) == 1

    def test_unsafe_context_interpolation_ok_recognized_as_top_level_key(
        self, tmp_path: Path
    ) -> None:
        """A YAML with top-level unsafe_context_interpolation_ok produces no
        Unknown-top-level warning."""
        loop_yaml = tmp_path / "loop.yaml"
        loop_yaml.write_text(
            "name: test-loop\n"
            "description: A loop that intentionally embeds raw context in shell\n"
            "initial: work\n"
            "unsafe_context_interpolation_ok: true\n"
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


class TestClassifyRouteDefault:
    """Classify-route-default WARNING check (ENH-2165)."""

    def _classify_fsm(
        self,
        *,
        with_default: bool = False,
        partial_route_ok: bool = False,
        with_route: bool = True,
    ) -> FSMLoop:
        from little_loops.fsm.schema import RouteConfig

        route: RouteConfig | None = None
        if with_route:
            route = RouteConfig(
                routes={"IMPLEMENT": "done", "WIRE": "done"},
                default="fallback" if with_default else None,
            )
        state_kwargs: dict = {
            "action": "classify.sh",
            "evaluate": EvaluateConfig(type="classify"),
        }
        if route is not None:
            state_kwargs["route"] = route
        return FSMLoop(
            name="test-loop",
            initial="classify",
            states={
                "classify": make_state(**state_kwargs),
                "done": make_state(terminal=True),
                "fallback": make_state(terminal=True),
            },
            partial_route_ok=partial_route_ok,
        )

    def test_warning_fires_when_default_absent(self) -> None:
        """WARNING fires for a classify state with a route: table and no default:."""
        fsm = self._classify_fsm(with_default=False)
        errors = _validate_classify_route_default(fsm)
        assert len(errors) == 1
        assert errors[0].severity == ValidationSeverity.WARNING
        assert "default" in errors[0].message

    def test_no_warning_when_default_present(self) -> None:
        """No warning when route: table has a default: entry."""
        fsm = self._classify_fsm(with_default=True)
        errors = _validate_classify_route_default(fsm)
        assert errors == []

    def test_no_warning_without_route_table(self) -> None:
        """No warning when classify state has no route: table at all."""
        fsm = self._classify_fsm(with_route=False)
        errors = _validate_classify_route_default(fsm)
        assert errors == []

    def test_suppressed_by_partial_route_ok(self) -> None:
        """partial_route_ok: true suppresses the classify-route-default warning."""
        fsm = self._classify_fsm(with_default=False, partial_route_ok=True)
        errors = _validate_classify_route_default(fsm)
        assert errors == []

    def test_wired_into_validate_fsm(self) -> None:
        """validate_fsm() includes the classify-route-default warning."""
        fsm = self._classify_fsm(with_default=False)
        errors = validate_fsm(fsm)
        classify_warnings = [
            e
            for e in errors
            if e.severity == ValidationSeverity.WARNING and "classify route" in e.message
        ]
        assert len(classify_warnings) == 1

    def test_non_classify_state_not_flagged(self) -> None:
        """States with other evaluator types are not flagged by this check."""
        fsm = FSMLoop(
            name="test-loop",
            initial="check",
            states={
                "check": make_state(
                    action="check.sh",
                    evaluate=EvaluateConfig(type="output_contains", pattern="OK"),
                    on_yes="done",
                    on_no="done",
                ),
                "done": make_state(terminal=True),
            },
        )
        errors = _validate_classify_route_default(fsm)
        assert errors == []


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


class TestLLMEvidenceContractValidation:
    """ENH-2342: MR-8 validation rule for LLM evidence contract in check_semantic states."""

    def _simple_fsm(self, **kwargs) -> FSMLoop:
        defaults: dict = {
            "name": "test-evidence",
            "initial": "check",
            "states": {
                "check": make_state(terminal=True),
            },
        }
        defaults.update(kwargs)
        return FSMLoop(**defaults)

    # --- positive controls ---

    def test_mr8_fires_for_llm_state_missing_evidence_keywords(self) -> None:
        """MR-8 WARNING fires when llm_structured prompt has no evidence keywords."""
        fsm = self._simple_fsm(
            states={
                "check": make_state(
                    action="run.sh",
                    evaluate=EvaluateConfig(
                        type="llm_structured",
                        prompt="Did the task complete successfully? Answer yes or no.",
                    ),
                    on_yes="done",
                    on_no="check",
                ),
                "done": make_state(terminal=True),
            }
        )
        errors = _validate_llm_evidence_contract(fsm)
        mr8_warnings = [
            e for e in errors if e.severity == ValidationSeverity.WARNING and "MR-8" in e.message
        ]
        assert len(mr8_warnings) == 1, f"Expected one MR-8 WARNING, got: {errors}"

    def test_mr8_does_not_fire_when_verbatim_present(self) -> None:
        """MR-8 does not fire when prompt contains 'verbatim'."""
        fsm = self._simple_fsm(
            states={
                "check": make_state(
                    action="run.sh",
                    evaluate=EvaluateConfig(
                        type="llm_structured",
                        prompt="Quote verbatim from the output to support your verdict.",
                    ),
                    on_yes="done",
                    on_no="check",
                ),
                "done": make_state(terminal=True),
            }
        )
        errors = _validate_llm_evidence_contract(fsm)
        mr8_warnings = [
            e for e in errors if e.severity == ValidationSeverity.WARNING and "MR-8" in e.message
        ]
        assert mr8_warnings == [], f"Unexpected MR-8 WARNING: {mr8_warnings}"

    def test_mr8_does_not_fire_when_evaluate_prompt_is_none(self) -> None:
        """MR-8 does not fire when evaluate.prompt is None — DEFAULT_LLM_PROMPT carries the contract."""
        fsm = self._simple_fsm(
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
        errors = _validate_llm_evidence_contract(fsm)
        mr8_warnings = [
            e for e in errors if e.severity == ValidationSeverity.WARNING and "MR-8" in e.message
        ]
        assert mr8_warnings == [], f"Unexpected MR-8 WARNING for None prompt: {mr8_warnings}"

    def test_mr8_does_not_fire_for_non_llm_evaluators(self) -> None:
        """MR-8 does not fire for exit_code evaluators."""
        fsm = self._simple_fsm(
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
        errors = _validate_llm_evidence_contract(fsm)
        mr8_warnings = [
            e for e in errors if e.severity == ValidationSeverity.WARNING and "MR-8" in e.message
        ]
        assert mr8_warnings == [], f"Unexpected MR-8 WARNING for exit_code: {mr8_warnings}"

    def test_mr8_suppressed_by_evidence_contract_ok(self) -> None:
        """evidence_contract_ok: true suppresses MR-8."""
        fsm = self._simple_fsm(
            evidence_contract_ok=True,
            states={
                "check": make_state(
                    action="run.sh",
                    evaluate=EvaluateConfig(
                        type="llm_structured",
                        prompt="Did the task complete? No evidence required.",
                    ),
                    on_yes="done",
                    on_no="check",
                ),
                "done": make_state(terminal=True),
            },
        )
        errors = _validate_llm_evidence_contract(fsm)
        assert errors == [], f"Unexpected errors with suppression flag: {errors}"

    def test_mr8_fires_end_to_end_via_validate_fsm(self) -> None:
        """MR-8 WARNING appears in validate_fsm() output (end-to-end wiring check)."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": make_state(
                    action="run.sh",
                    evaluate=EvaluateConfig(
                        type="llm_structured",
                        prompt="Did the task complete? Answer yes or no.",
                    ),
                    on_yes="done",
                    on_no="check",
                ),
                "done": make_state(terminal=True),
            },
        )
        all_errors = validate_fsm(fsm)
        mr8_warnings = [
            e
            for e in all_errors
            if e.severity == ValidationSeverity.WARNING and "MR-8" in e.message
        ]
        assert len(mr8_warnings) >= 1, (
            f"MR-8 WARNING not found in validate_fsm output: {all_errors}"
        )


# ---------------------------------------------------------------------------
# MR-10 — parse-swallow detector
# ---------------------------------------------------------------------------

_SWALLOW_ACTION = """\
import json, sys
text = open("data.json").read()
try:
    data = json.loads(text)
except json.JSONDecodeError:
    sys.exit(0)
print(data)
"""

_SWALLOW_ACTION_VALUE_ERROR = """\
import json, sys
text = open("data.json").read()
try:
    data = json.loads(text)
except ValueError:
    exit(0)
print(data)
"""


class TestParseSwallow:
    """MR-10: shell state silently swallows a JSON parse failure with exit 0."""

    def _simple_fsm(
        self,
        action: str,
        *,
        action_type: str | None = "shell",
        on_error: str | None = None,
        parse_swallow_ok: bool = False,
    ) -> FSMLoop:
        state_kwargs: dict = {
            "action": action,
            "action_type": action_type,
            "on_yes": "done",
            "on_no": "work",
        }
        if on_error is not None:
            state_kwargs["on_error"] = on_error
        return FSMLoop(
            name="test-loop",
            initial="work",
            states={
                "work": make_state(**state_kwargs),
                "done": make_state(terminal=True),
            },
            parse_swallow_ok=parse_swallow_ok,
        )

    def test_mr10_fires_for_explicit_zero_exit(self) -> None:
        """MR-10 WARNING fires for json.loads + except JSONDecodeError + sys.exit(0)."""
        fsm = self._simple_fsm(_SWALLOW_ACTION)
        errors = _validate_parse_swallow(fsm)
        assert len(errors) == 1
        assert errors[0].severity == ValidationSeverity.WARNING
        assert errors[0].path == "states.work.action"
        assert "MR-10" in errors[0].message

    def test_mr10_fires_for_value_error_variant(self) -> None:
        """MR-10 WARNING fires when ValueError is caught and exit(0) is used."""
        fsm = self._simple_fsm(_SWALLOW_ACTION_VALUE_ERROR)
        errors = _validate_parse_swallow(fsm)
        assert len(errors) == 1
        assert errors[0].severity == ValidationSeverity.WARNING

    def test_mr10_clean_with_on_error_route(self) -> None:
        """MR-10 does not fire when on_error: is present on the state."""
        fsm = self._simple_fsm(_SWALLOW_ACTION, on_error="handle_error")
        errors = _validate_parse_swallow(fsm)
        assert errors == []

    def test_mr10_suppressed_by_parse_swallow_ok(self) -> None:
        """parse_swallow_ok: true suppresses MR-10."""
        fsm = self._simple_fsm(_SWALLOW_ACTION, parse_swallow_ok=True)
        errors = _validate_parse_swallow(fsm)
        assert errors == []

    def test_mr10_does_not_fire_without_json_parse_call(self) -> None:
        """MR-10 does not fire when there is no json.loads/json.load call."""
        action = "import sys\ntry:\n    pass\nexcept ValueError:\n    sys.exit(0)\n"
        fsm = self._simple_fsm(action)
        errors = _validate_parse_swallow(fsm)
        assert errors == []

    def test_mr10_does_not_fire_for_prompt_action(self) -> None:
        """MR-10 ignores prompt-type actions (only shell is relevant)."""
        fsm = self._simple_fsm(_SWALLOW_ACTION, action_type="prompt")
        errors = _validate_parse_swallow(fsm)
        assert errors == []

    def test_mr10_does_not_fire_without_except_clause(self) -> None:
        """MR-10 does not fire when there is no except clause catching the right exceptions."""
        action = "import json, sys\ndata = json.loads(open('f').read())\nsys.exit(0)\n"
        fsm = self._simple_fsm(action)
        errors = _validate_parse_swallow(fsm)
        assert errors == []

    def test_mr10_wired_into_validate_fsm(self) -> None:
        """validate_fsm() includes MR-10 WARNING for parse-swallow pattern."""
        fsm = self._simple_fsm(_SWALLOW_ACTION)
        all_errors = validate_fsm(fsm)
        mr10 = [
            e
            for e in all_errors
            if e.severity == ValidationSeverity.WARNING and "(MR-10)" in e.message
        ]
        assert len(mr10) == 1

    def test_mr10_parse_swallow_ok_recognized_as_top_level_key(self, tmp_path: Path) -> None:
        """A YAML with top-level parse_swallow_ok produces no Unknown-top-level warning."""
        loop_yaml = tmp_path / "loop.yaml"
        loop_yaml.write_text(
            "name: test-loop\n"
            "description: Intentionally swallows parse errors\n"
            "initial: work\n"
            "parse_swallow_ok: true\n"
            "states:\n"
            "  work:\n"
            "    action: run.sh\n"
            "    on_yes: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        from little_loops.fsm.validation import load_and_validate

        _, warnings = load_and_validate(loop_yaml, raise_on_error=False)
        unknown = [w for w in warnings if "Unknown top-level" in w.message]
        assert unknown == [], f"parse_swallow_ok flagged as unknown: {unknown}"


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
