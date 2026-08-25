"""Tests for FSM validation structural rule family: schema-shape checks not
gated by a numbered MR suppress flag, plus reachability analysis and routing
validation (including extra_routes), and the validate_fsm/load_and_validate
entry points.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from little_loops.fsm.schema import (
    ArtifactOutput,
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
    _validate_abstention_route,
    _validate_evaluator,
    _validate_failure_terminal_action,
    _validate_input_key_without_guard,
    _validate_missing_scope,
    _validate_parameters,
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


class TestArtifactModeValidation:
    """FEAT-3318: a template-capable loop must declare artifact_output."""

    def _make_fsm(self, **kwargs) -> FSMLoop:
        return FSMLoop(
            name="test",
            initial="s",
            states={"s": make_state(terminal=True)},
            **kwargs,
        )

    def test_template_mode_without_artifact_output_rejected(self) -> None:
        fsm = self._make_fsm(artifact_mode="template")
        errors = validate_fsm(fsm)
        error_errors = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        assert any("artifact_mode" in (e.path or "") for e in error_errors)

    def test_template_mode_with_artifact_output_accepted(self) -> None:
        fsm = self._make_fsm(
            artifact_mode="template",
            artifact_output=ArtifactOutput(from_path="output.llat"),
        )
        errors = validate_fsm(fsm)
        assert not any("artifact_mode" in (e.path or "") for e in errors)

    def test_context_template_var_without_artifact_output_rejected(self) -> None:
        """context: {artifact_mode: template} is also template-capable."""
        fsm = self._make_fsm(context={"artifact_mode": "template"})
        errors = validate_fsm(fsm)
        error_errors = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        assert any("artifact_mode" in (e.path or "") for e in error_errors)

    def test_context_file_var_without_artifact_output_rejected(self) -> None:
        """context: {artifact_mode: file} — the html-anything shape — is also
        template-capable (selectable via --context), so it too requires
        artifact_output even though its effective mode is "file"."""
        fsm = self._make_fsm(context={"artifact_mode": "file"})
        errors = validate_fsm(fsm)
        error_errors = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        assert any("artifact_mode" in (e.path or "") for e in error_errors)

    def test_file_mode_no_context_var_no_error(self) -> None:
        """A plain file-mode loop with no artifact_mode context key is unaffected."""
        fsm = self._make_fsm()
        errors = validate_fsm(fsm)
        assert not any("artifact_mode" in (e.path or "") for e in errors)

    def test_no_suppression_flag_exists(self) -> None:
        fsm = self._make_fsm(artifact_mode="template")
        assert not hasattr(fsm, "artifact_mode_ok")

    def test_non_llat_destination_warns(self) -> None:
        fsm = self._make_fsm(
            artifact_mode="template",
            artifact_output=ArtifactOutput(from_path="output", to="somewhere-else"),
        )
        errors = validate_fsm(fsm)
        warnings = [e for e in errors if e.severity == ValidationSeverity.WARNING]
        assert any("artifact_output.to" in (e.path or "") for e in warnings)

    def test_llat_destination_no_warning(self) -> None:
        fsm = self._make_fsm(
            artifact_mode="template",
            artifact_output=ArtifactOutput(from_path="output", to="my-template.llat"),
        )
        errors = validate_fsm(fsm)
        assert not any("artifact_output.to" in (e.path or "") for e in errors)


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


class TestEffortStateValidation:
    """ENH-2869: effort: override validation — mirrors TestModelStateValidation."""

    def test_effort_on_shell_state_emits_warning(self) -> None:
        """effort: on a shell state emits a validation WARNING."""
        fsm = FSMLoop(
            name="test-loop",
            initial="work",
            states={
                "work": StateConfig(
                    action="echo hi",
                    action_type="shell",
                    effort="low",
                    next="done",
                ),
                "done": make_state(terminal=True),
            },
        )
        errors = _validate_state_action("work", fsm.states["work"])
        warnings = [e for e in errors if e.severity == ValidationSeverity.WARNING]
        assert any("effort" in w.message and "ignored" in w.message for w in warnings)

    def test_effort_on_prompt_state_no_warning(self) -> None:
        """effort: on a prompt state does not emit a warning."""
        fsm = FSMLoop(
            name="test-loop",
            initial="work",
            states={
                "work": StateConfig(
                    action="/ll:test",
                    action_type="prompt",
                    effort="low",
                    next="done",
                ),
                "done": make_state(terminal=True),
            },
        )
        errors = _validate_state_action("work", fsm.states["work"])
        effort_warnings = [
            e for e in errors if e.severity == ValidationSeverity.WARNING and "effort" in e.message
        ]
        assert effort_warnings == []

    def test_effort_on_mcp_tool_state_emits_warning(self) -> None:
        """effort: on an mcp_tool state emits a validation WARNING."""
        state = StateConfig(
            action="server/tool",
            action_type="mcp_tool",
            effort="high",
            next="done",
        )
        errors = _validate_state_action("check", state)
        warnings = [e for e in errors if e.severity == ValidationSeverity.WARNING]
        assert any("effort" in w.message and "ignored" in w.message for w in warnings)

    def test_effort_on_shell_state_with_llm_structured_evaluate_no_warning(self) -> None:
        """effort: on a shell state paired with an llm_structured evaluate block
        does not fire the "ignored" WARNING, mirroring model's ENH-2713 exemption."""
        state = StateConfig(
            action="run.sh",
            action_type="shell",
            effort="low",
            evaluate=EvaluateConfig(type="llm_structured"),
            on_yes="done",
            on_no="work",
        )
        errors = _validate_state_action("work", state)
        effort_warnings = [
            e for e in errors if e.severity == ValidationSeverity.WARNING and "effort" in e.message
        ]
        assert effort_warnings == []


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


class TestMissingScopeValidation:
    """Tests for _validate_missing_scope (BUG-3107)."""

    def _make_fsm(self, scope: list[str] | None = None) -> FSMLoop:
        return FSMLoop(
            name="test",
            initial="start",
            states={"start": make_state(terminal=True)},
            scope=scope or [],
        )

    def test_warning_fires_when_scope_missing(self) -> None:
        """WARNING emitted when a loop declares no scope: at all."""
        fsm = self._make_fsm(scope=[])
        errors = _validate_missing_scope(fsm)
        assert len(errors) == 1
        assert errors[0].severity == ValidationSeverity.WARNING
        assert errors[0].path == "scope"

    def test_no_warning_when_scope_present(self) -> None:
        """No WARNING when scope: names specific paths."""
        fsm = self._make_fsm(scope=["src/"])
        errors = _validate_missing_scope(fsm)
        assert errors == []

    def test_no_warning_for_explicit_repo_wide_scope(self) -> None:
        """No WARNING when scope: [\".\"] is the explicit repo-wide opt-in."""
        fsm = self._make_fsm(scope=["."])
        errors = _validate_missing_scope(fsm)
        assert errors == []

    def test_warning_wired_into_validate_fsm(self) -> None:
        """_validate_missing_scope is wired into validate_fsm."""
        fsm = self._make_fsm(scope=[])
        all_errors = validate_fsm(fsm)
        scope_warnings = [
            e for e in all_errors if e.severity == ValidationSeverity.WARNING and e.path == "scope"
        ]
        assert len(scope_warnings) == 1

    def test_no_warning_when_scope_wired_into_validate_fsm(self) -> None:
        """validate_fsm emits no scope WARNING when scope: is declared."""
        fsm = self._make_fsm(scope=["src/"])
        all_errors = validate_fsm(fsm)
        scope_warnings = [
            e for e in all_errors if e.severity == ValidationSeverity.WARNING and e.path == "scope"
        ]
        assert scope_warnings == []


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


class TestFailureTerminalActionFlagDriven:
    """ENH-2814: _validate_failure_terminal_action reads the `failure` flag."""

    def _fsm(self, terminal_states: dict[str, StateConfig]) -> FSMLoop:
        states: dict[str, StateConfig] = {
            "start": StateConfig(action="echo hi", next=next(iter(terminal_states))),
        }
        states.update(terminal_states)
        return FSMLoop(name="t", initial="start", states=states)

    def test_bare_flagged_terminal_warns_regardless_of_name(self) -> None:
        """A flagged terminal named outside the legacy set is now covered."""
        fsm = FSMLoop(
            name="t",
            initial="check",
            states={
                # No action and no sub-loop → not a diagnostic predecessor.
                "check": StateConfig(next="blocked"),
                "blocked": StateConfig(terminal=True, failure=True),
            },
        )
        errors = _validate_failure_terminal_action(fsm)
        assert [e.path for e in errors] == ["states.blocked"]
        assert errors[0].severity is ValidationSeverity.WARNING

    def test_unflagged_terminal_named_failed_is_not_flagged_twice(self) -> None:
        """An explicit `failure: false` opts a `failed`-named terminal out."""
        fsm = FSMLoop(
            name="t",
            initial="check",
            states={
                "check": StateConfig(next="failed"),
                "failed": StateConfig(terminal=True, failure=False),
            },
        )
        assert _validate_failure_terminal_action(fsm) == []

    def test_diagnostic_predecessor_suppresses_warning(self) -> None:
        """A predecessor carrying an action counts as diagnostic output."""
        fsm = FSMLoop(
            name="t",
            initial="diagnose",
            states={
                "diagnose": StateConfig(action="echo why", next="blocked"),
                "blocked": StateConfig(terminal=True, failure=True),
            },
        )
        assert _validate_failure_terminal_action(fsm) == []

    def test_learning_predecessor_counts_as_diagnostic(self) -> None:
        """A `learning:` state is action-bearing (it shells out to ll-learning-tests)."""
        fsm = FSMLoop(
            name="t",
            initial="prove",
            states={
                "prove": StateConfig(
                    learning=LearningConfig(targets_csv="httpx"),
                    on_yes="done",
                    on_blocked="blocked",
                ),
                "done": StateConfig(terminal=True),
                "blocked": StateConfig(terminal=True, failure=True),
            },
        )
        assert _validate_failure_terminal_action(fsm) == []

    def test_name_convention_still_defaults_the_flag_through_yaml(self) -> None:
        """A YAML `failed` terminal with no `failure:` key is still validated."""
        fsm = FSMLoop.from_dict(
            {
                "name": "t",
                "initial": "check",
                "states": {
                    "check": {"next": "failed"},
                    "failed": {"terminal": True},
                },
            }
        )
        assert [e.path for e in _validate_failure_terminal_action(fsm)] == ["states.failed"]


# ---------------------------------------------------------------------------
# MR-13 (ENH-2860) — abandonment must reach summary.json and downgrade verdict
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# ENH-3222 — abstention-capable states need a cannot_judge or error route
# ---------------------------------------------------------------------------


class TestAbstentionRouteValidation:
    """ENH-3222: judged gates that can abstain need a cannot_judge/error route."""

    def _simple_fsm(self, **kwargs) -> FSMLoop:
        defaults: dict = {
            "name": "test-abstention",
            "initial": "check",
            "states": {
                "check": make_state(terminal=True),
            },
        }
        defaults.update(kwargs)
        return FSMLoop(**defaults)

    def test_fires_for_llm_structured_with_no_route(self) -> None:
        """An explicit llm_structured judge with no cannot_judge/error route dead-ends."""
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
        errors = _validate_abstention_route(fsm)
        assert len(errors) == 1
        assert errors[0].severity == ValidationSeverity.WARNING
        assert errors[0].path == "states.check"

    def test_does_not_fire_when_on_cannot_judge_declared(self) -> None:
        fsm = self._simple_fsm(
            states={
                "check": make_state(
                    action="run.sh",
                    evaluate=EvaluateConfig(type="llm_structured"),
                    on_yes="done",
                    on_no="check",
                    extra_routes={"cannot_judge": "check"},
                ),
                "done": make_state(terminal=True),
            }
        )
        assert _validate_abstention_route(fsm) == []

    def test_does_not_fire_when_error_route_declared(self) -> None:
        fsm = self._simple_fsm(
            states={
                "check": make_state(
                    action="run.sh",
                    evaluate=EvaluateConfig(type="llm_structured"),
                    on_yes="done",
                    on_no="check",
                    on_error="check",
                ),
                "done": make_state(terminal=True),
            }
        )
        assert _validate_abstention_route(fsm) == []

    def test_route_default_does_not_rescue(self) -> None:
        """route.default is never consulted by _abstention_fallback(); must still fire."""
        from little_loops.fsm.schema import RouteConfig

        fsm = self._simple_fsm(
            states={
                "check": make_state(
                    action="run.sh",
                    evaluate=EvaluateConfig(type="llm_structured"),
                    route=RouteConfig(routes={"yes": "done"}, default="check"),
                ),
                "done": make_state(terminal=True),
            }
        )
        errors = _validate_abstention_route(fsm)
        assert len(errors) == 1

    def test_cannot_judge_uncertain_route_does_not_satisfy_base_key(self) -> None:
        """Declaring only on_cannot_judge_uncertain still dead-ends on a bare cannot_judge."""
        fsm = self._simple_fsm(
            states={
                "check": make_state(
                    action="run.sh",
                    evaluate=EvaluateConfig(type="llm_structured"),
                    on_yes="done",
                    extra_routes={"cannot_judge_uncertain": "check"},
                ),
                "done": make_state(terminal=True),
            }
        )
        errors = _validate_abstention_route(fsm)
        assert len(errors) == 1

    def test_fires_for_abstain_on_exit_3_state(self) -> None:
        """ENH-3224's flag-gated exit_code abstention is covered too."""
        fsm = self._simple_fsm(
            states={
                "check": make_state(
                    action="run.sh",
                    evaluate=EvaluateConfig(type="exit_code", abstain_on_exit_3=True),
                    on_yes="done",
                    on_no="check",
                ),
                "done": make_state(terminal=True),
            }
        )
        errors = _validate_abstention_route(fsm)
        assert len(errors) == 1

    def test_does_not_fire_for_exit_code_without_abstain_flag(self) -> None:
        """A plain exit_code evaluator (no abstain_on_exit_3) cannot abstain."""
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
        assert _validate_abstention_route(fsm) == []

    def test_does_not_fire_for_non_judged_state(self) -> None:
        fsm = self._simple_fsm(
            states={
                "check": make_state(
                    action="run.sh",
                    evaluate=EvaluateConfig(type="output_contains", pattern="ok"),
                    on_yes="done",
                    on_no="check",
                ),
                "done": make_state(terminal=True),
            }
        )
        assert _validate_abstention_route(fsm) == []

    def test_suppressed_by_abstention_route_ok(self) -> None:
        fsm = self._simple_fsm(
            abstention_route_ok=True,
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
        assert _validate_abstention_route(fsm) == []

    def test_fires_end_to_end_via_validate_fsm(self) -> None:
        fsm = FSMLoop(
            name="test",
            initial="check",
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
        all_errors = validate_fsm(fsm)
        abstention_warnings = [
            e
            for e in all_errors
            if e.severity == ValidationSeverity.WARNING and "ENH-3222" in e.message
        ]
        assert len(abstention_warnings) >= 1, (
            f"ENH-3222 WARNING not found in validate_fsm output: {all_errors}"
        )
