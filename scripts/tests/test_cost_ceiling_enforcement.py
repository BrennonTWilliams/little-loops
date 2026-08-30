"""Tests for runtime enforcement of per-state cost_ceiling (BUG-3360).

Follows the end-to-end run() pattern established by
TestExecutorRssBudget (test_host_guard.py) rather than unit-testing
_check_cost_ceiling directly: build a minimal FSM, drive a real run(),
and assert on result.terminated_by / the emitted events.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from little_loops.fsm.executor import ActionResult, FSMExecutor
from little_loops.fsm.persistence import PersistentExecutor
from little_loops.fsm.schema import CostCeilingConfig, EvaluateConfig, FSMLoop, StateConfig
from little_loops.subprocess_utils import TokenUsage


class MockActionRunner:
    """Action runner that returns pre-configured results in sequence."""

    def __init__(self, results: list[ActionResult]) -> None:
        self.results = results
        self._index = 0

    def run(self, action: str, timeout: int, is_slash_command: bool, **kwargs: Any) -> ActionResult:
        del action, timeout, is_slash_command, kwargs
        result = self.results[min(self._index, len(self.results) - 1)]
        self._index += 1
        return result


def _usage_result(
    input_tokens: int, output_tokens: int, model: str = "claude-sonnet-4-6"
) -> ActionResult:
    usage = TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=0,
        cache_creation_tokens=0,
        model=model,
    )
    return ActionResult(output="yes", stderr="", exit_code=0, duration_ms=10, usage_events=[usage])


@pytest.fixture
def tmp_loops_dir(tmp_path: Path) -> Path:
    return tmp_path / ".loops"


def collect_events(persistent: PersistentExecutor) -> list[dict[str, Any]]:
    """Wrap the inner FSMExecutor's event_callback to also collect events,
    without disabling PersistentExecutor's own usage.jsonl writer."""
    events: list[dict[str, Any]] = []
    inner_callback = persistent._executor.event_callback

    def wrapper(event: dict[str, Any]) -> None:
        events.append(event)
        inner_callback(event)

    persistent._executor.event_callback = wrapper
    return events


class TestCostCeilingBreachAborts:
    def test_breach_aborts_with_terminated_by(self, tmp_path: Path, tmp_loops_dir: Path) -> None:
        run_dir = str(tmp_path / "run_dir") + "/"
        Path(run_dir).mkdir(parents=True, exist_ok=True)
        fsm = FSMLoop(
            name="cc-breach",
            initial="work",
            states={
                "work": StateConfig(
                    action="/do-work",
                    action_type="prompt",
                    evaluate=EvaluateConfig(type="exit_code"),
                    on_yes="done",
                    on_no="done",
                    cost_ceiling=CostCeilingConfig(cost_ceiling_per_state=1.0),
                ),
                "done": StateConfig(terminal=True),
            },
            context={"run_dir": run_dir},
        )
        # 1,000,000 input tokens @ $3/M = $3.00 > $1.00 ceiling.
        runner = MockActionRunner(results=[_usage_result(1_000_000, 0)])
        executor = PersistentExecutor(fsm, loops_dir=tmp_loops_dir, action_runner=runner)
        events = collect_events(executor)

        result = executor.run()

        assert result.terminated_by == "cost_ceiling_exceeded"
        assert result.error is not None
        assert "1.0" in result.error
        breaches = [e for e in events if e["event"] == "cost_ceiling_exceeded"]
        assert len(breaches) == 1
        assert breaches[0]["action"] == "abort"
        assert breaches[0]["state"] == "work"
        assert breaches[0]["cost_usd"] == pytest.approx(3.0)

    def test_under_ceiling_completes_normally(self, tmp_path: Path, tmp_loops_dir: Path) -> None:
        run_dir = str(tmp_path / "run_dir") + "/"
        Path(run_dir).mkdir(parents=True, exist_ok=True)
        fsm = FSMLoop(
            name="cc-under",
            initial="work",
            states={
                "work": StateConfig(
                    action="/do-work",
                    action_type="prompt",
                    evaluate=EvaluateConfig(type="exit_code"),
                    on_yes="done",
                    on_no="done",
                    cost_ceiling=CostCeilingConfig(cost_ceiling_per_state=10.0),
                ),
                "done": StateConfig(terminal=True),
            },
            context={"run_dir": run_dir},
        )
        runner = MockActionRunner(results=[_usage_result(1_000_000, 0)])  # $3.00 < $10.00
        executor = PersistentExecutor(fsm, loops_dir=tmp_loops_dir, action_runner=runner)
        events = collect_events(executor)

        result = executor.run()

        assert result.terminated_by == "terminal"
        assert not [e for e in events if e["event"] == "cost_ceiling_exceeded"]


class TestCostCeilingWarnOnce:
    def test_warn_fires_once_per_state_across_revisits(
        self, tmp_path: Path, tmp_loops_dir: Path
    ) -> None:
        run_dir = str(tmp_path / "run_dir") + "/"
        Path(run_dir).mkdir(parents=True, exist_ok=True)
        fsm = FSMLoop(
            name="cc-warn",
            initial="work",
            states={
                "work": StateConfig(
                    action="/do-work",
                    action_type="prompt",
                    evaluate=EvaluateConfig(type="exit_code"),
                    on_yes="work",
                    max_retries=2,
                    on_retry_exhausted="done",
                    cost_ceiling=CostCeilingConfig(cost_warn_at=1.0),
                ),
                "done": StateConfig(terminal=True),
            },
            context={"run_dir": run_dir},
        )
        # $3.00/visit, well above warn_at=1.0 on every one of the 3 visits.
        runner = MockActionRunner(
            results=[
                _usage_result(1_000_000, 0),
                _usage_result(1_000_000, 0),
                _usage_result(1_000_000, 0),
            ]
        )
        executor = PersistentExecutor(fsm, loops_dir=tmp_loops_dir, action_runner=runner)
        events = collect_events(executor)

        result = executor.run()

        assert result.terminated_by == "terminal"
        warns = [e for e in events if e["event"] == "cost_ceiling_warn"]
        assert len(warns) == 1
        assert not [e for e in events if e["event"] == "cost_ceiling_exceeded"]


class TestCostCeilingUnknownCases:
    def test_missing_usage_jsonl_does_not_abort(self, tmp_path: Path) -> None:
        """A bare FSMExecutor.run() (no PersistentExecutor) never writes
        usage.jsonl — the ceiling must be treated as unknown, not zero."""
        fsm = FSMLoop(
            name="cc-no-run-dir",
            initial="work",
            states={
                "work": StateConfig(
                    action="/do-work",
                    action_type="prompt",
                    evaluate=EvaluateConfig(type="exit_code"),
                    on_yes="done",
                    on_no="done",
                    cost_ceiling=CostCeilingConfig(cost_ceiling_per_state=0.001),
                ),
                "done": StateConfig(terminal=True),
            },
        )
        runner = MockActionRunner(results=[_usage_result(1_000_000, 0)])
        executor = FSMExecutor(fsm, action_runner=runner)
        events: list[dict[str, Any]] = []
        executor.event_callback = events.append

        result = executor.run()

        assert result.terminated_by == "terminal"
        unknowns = [e for e in events if e["event"] == "cost_ceiling_unknown"]
        assert len(unknowns) == 1
        assert unknowns[0]["reason"] == "usage.jsonl unavailable"

    def test_unpriceable_model_does_not_abort(self, tmp_path: Path, tmp_loops_dir: Path) -> None:
        run_dir = str(tmp_path / "run_dir") + "/"
        Path(run_dir).mkdir(parents=True, exist_ok=True)
        fsm = FSMLoop(
            name="cc-unknown-model",
            initial="work",
            states={
                "work": StateConfig(
                    action="/do-work",
                    action_type="prompt",
                    evaluate=EvaluateConfig(type="exit_code"),
                    on_yes="done",
                    on_no="done",
                    cost_ceiling=CostCeilingConfig(cost_ceiling_per_state=0.0),
                ),
                "done": StateConfig(terminal=True),
            },
            context={"run_dir": run_dir},
        )
        runner = MockActionRunner(
            results=[_usage_result(1_000_000, 0, model="totally-unpriced-model-xyz")]
        )
        executor = PersistentExecutor(fsm, loops_dir=tmp_loops_dir, action_runner=runner)
        events = collect_events(executor)

        result = executor.run()

        assert result.terminated_by == "terminal"
        unknowns = [e for e in events if e["event"] == "cost_ceiling_unknown"]
        assert len(unknowns) == 1
        assert unknowns[0]["reason"] == "unpriceable model"
        assert not [e for e in events if e["event"] == "cost_ceiling_exceeded"]


class TestCostCeilingNoOp:
    def test_no_ceiling_declared_is_a_no_op(self, tmp_path: Path, tmp_loops_dir: Path) -> None:
        run_dir = str(tmp_path / "run_dir") + "/"
        Path(run_dir).mkdir(parents=True, exist_ok=True)
        fsm = FSMLoop(
            name="cc-none",
            initial="work",
            states={
                "work": StateConfig(
                    action="/do-work",
                    action_type="prompt",
                    evaluate=EvaluateConfig(type="exit_code"),
                    on_yes="done",
                    on_no="done",
                ),
                "done": StateConfig(terminal=True),
            },
            context={"run_dir": run_dir},
        )
        runner = MockActionRunner(results=[_usage_result(1_000_000, 0)])
        executor = PersistentExecutor(fsm, loops_dir=tmp_loops_dir, action_runner=runner)
        events = collect_events(executor)

        result = executor.run()

        assert result.terminated_by == "terminal"
        assert not [
            e
            for e in events
            if e["event"] in ("cost_ceiling_exceeded", "cost_ceiling_warn", "cost_ceiling_unknown")
        ]
