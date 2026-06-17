"""Shared test helpers for FSM loop tests.

These were previously duplicated across 6 test files. They live here so
all loop/FSM tests can import them from a single source.
"""

from __future__ import annotations

from little_loops.fsm.schema import (
    EvaluateConfig,
    FSMLoop,
    RouteConfig,
    StateConfig,
)


def make_test_state(
    action: str | None = None,
    on_yes: str | None = None,
    on_no: str | None = None,
    on_error: str | None = None,
    next: str | None = None,
    terminal: bool = False,
    evaluate: EvaluateConfig | None = None,
    route: RouteConfig | None = None,
    capture: str | None = None,
    timeout: int | None = None,
    on_maintain: str | None = None,
    model: str | None = None,
) -> StateConfig:
    """Create a StateConfig for testing.

    Provides sensible defaults so individual tests only specify the
    fields they care about.
    """
    return StateConfig(
        action=action,
        on_yes=on_yes,
        on_no=on_no,
        on_error=on_error,
        next=next,
        terminal=terminal,
        evaluate=evaluate,
        route=route,
        capture=capture,
        timeout=timeout,
        on_maintain=on_maintain,
        model=model,
    )


def make_test_fsm(
    name: str = "test-loop",
    initial: str = "start",
    states: dict[str, StateConfig] | None = None,
    max_steps: int = 50,
    timeout: int | None = None,
) -> FSMLoop:
    """Create an FSMLoop for testing.

    If no states are provided, creates a minimal two-state loop
    (start → done).
    """
    if states is None:
        states = {
            "start": make_test_state(action="echo start", on_yes="done", on_no="done"),
            "done": make_test_state(terminal=True),
        }
    return FSMLoop(
        name=name,
        initial=initial,
        states=states,
        max_steps=max_steps,
        timeout=timeout,
    )
