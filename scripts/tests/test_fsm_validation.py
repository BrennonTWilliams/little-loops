"""Tests for FSM validation logic.

Tests cover reachability analysis and routing validation, including
support for custom on_<verdict> routing via extra_routes.
"""

from __future__ import annotations

from little_loops.fsm.schema import FSMLoop, StateConfig
from little_loops.fsm.validation import ValidationSeverity, validate_fsm


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
