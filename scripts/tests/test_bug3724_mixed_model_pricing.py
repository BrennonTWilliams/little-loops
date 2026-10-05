"""BUG-3724: mixed-model / mixed-batch / cross-date action usage is priced per contribution."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from little_loops import pricing
from little_loops.fsm.cost_graph import CostReport, build_usage_contributions
from little_loops.fsm.executor import ActionResult
from little_loops.fsm.persistence import PersistentExecutor
from little_loops.fsm.schema import CostCeilingConfig, EvaluateConfig, FSMLoop, StateConfig
from little_loops.pricing import estimate_cost_usd
from little_loops.subprocess_utils import TokenUsage

M = 1_000_000


def _usage(
    model: str,
    input_tokens: int | None = M,
    *,
    is_batch: bool = False,
    observed_at: str | None = None,
) -> TokenUsage:
    return TokenUsage(
        input_tokens=input_tokens,
        output_tokens=0,
        cache_read_tokens=0,
        cache_creation_tokens=0,
        model=model,
        is_batch=is_batch,
        observed_at=observed_at,
    )


class _Runner:
    def __init__(self, events: list[TokenUsage]) -> None:
        self.events = events

    def run(self, action: str, timeout: int, is_slash_command: bool, **kwargs: Any) -> ActionResult:
        return ActionResult(
            output="yes", stderr="", exit_code=0, duration_ms=10, usage_events=self.events
        )


def _run(
    tmp_path: Path, events: list[TokenUsage], ceiling: float | None = None
) -> tuple[Path, list[dict[str, Any]]]:
    run_dir = tmp_path / "run_dir"
    run_dir.mkdir()
    fsm = FSMLoop(
        name="mixed",
        initial="work",
        states={
            "work": StateConfig(
                action="/do-work",
                action_type="prompt",
                evaluate=EvaluateConfig(type="exit_code"),
                on_yes="done",
                on_no="done",
                cost_ceiling=(
                    CostCeilingConfig(cost_ceiling_per_state=ceiling) if ceiling else None
                ),
            ),
            "done": StateConfig(terminal=True),
        },
        context={"run_dir": f"{run_dir}/"},
    )
    executor = PersistentExecutor(fsm, loops_dir=tmp_path / ".loops", action_runner=_Runner(events))
    collected: list[dict[str, Any]] = []
    inner = executor._executor.event_callback

    def wrapper(event: dict[str, Any]) -> None:
        collected.append(event)
        inner(event)

    executor._executor.event_callback = wrapper
    executor.run()
    return run_dir / "usage.jsonl", collected


def _state_cost(usage: Path) -> tuple[float | None, int]:
    report = CostReport.from_usage_jsonl(usage)
    (state,) = report.states
    return state.cost_usd, state.iterations


class TestMixedModel:
    @pytest.mark.parametrize("reverse", [False, True])
    def test_mixed_models_priced_per_event(self, tmp_path: Path, reverse: bool) -> None:
        events = [_usage("claude-haiku-4-5"), _usage("claude-sonnet-5")]
        if reverse:
            events.reverse()
        usage, _ = _run(tmp_path, events)
        expected = estimate_cost_usd("claude-haiku-4-5", M, 0, 0, 0) + estimate_cost_usd(
            "claude-sonnet-5", M, 0, 0, 0
        )
        cost, iterations = _state_cost(usage)
        assert cost == pytest.approx(expected)
        assert iterations == 1  # one action stays one iteration
        row = json.loads(usage.read_text().splitlines()[0])
        assert row["input_tokens"] == 2 * M  # audit aggregate preserved, not re-priced
        assert len(row["usage_contributions"]) == 2

    def test_same_model_mixed_batch(self, tmp_path: Path) -> None:
        usage, _ = _run(
            tmp_path,
            [_usage("claude-haiku-4-5"), _usage("claude-haiku-4-5", is_batch=True)],
        )
        cost, _ = _state_cost(usage)
        assert cost == pytest.approx(1.0 + 0.5)

    def test_homogeneous_parity(self, tmp_path: Path) -> None:
        usage, _ = _run(tmp_path, [_usage("claude-haiku-4-5"), _usage("claude-haiku-4-5")])
        cost, _ = _state_cost(usage)
        assert cost == pytest.approx(2.0)
        row = json.loads(usage.read_text().splitlines()[0])
        assert len(row["usage_contributions"]) == 1
        assert row["usage_contributions"][0]["usage_event_count"] == 2

    def test_unknown_model_makes_cost_unavailable_keeps_tokens(self, tmp_path: Path) -> None:
        usage, _ = _run(tmp_path, [_usage("claude-sonnet-5-5"), _usage("claude-haiku-4-5")])
        report = CostReport.from_usage_jsonl(usage)
        (state,) = report.states
        assert state.cost_usd is None
        assert state.unavailable_reason == "unpriceable model"
        assert state.input_tokens == 2 * M
        assert report.totals["cost_usd"] is None

    def test_incomplete_component_unavailable(self, tmp_path: Path) -> None:
        usage, _ = _run(tmp_path, [_usage("claude-haiku-4-5"), _usage("claude-sonnet-5", None)])
        (state,) = CostReport.from_usage_jsonl(usage).states
        assert state.cost_usd is None
        assert state.input_tokens == M
        assert state.input_tokens_missing == 1

    def test_stable_json_has_no_new_keys(self, tmp_path: Path) -> None:
        usage, _ = _run(tmp_path, [_usage("claude-haiku-4-5"), _usage("claude-sonnet-5")])
        data = CostReport.from_usage_jsonl(usage).to_dict()
        assert "unavailable_reason" not in data["states"][0]
        assert "usage_contributions" not in data["states"][0]


class TestCeiling:
    def test_mixed_cost_enforced_at_correct_total(self, tmp_path: Path) -> None:
        # Correct total is $3 (> $2.5); pricing all at haiku's $1/M would be $2.
        usage, events = _run(
            tmp_path, [_usage("claude-haiku-4-5"), _usage("claude-sonnet-5")], ceiling=2.5
        )
        assert [e for e in events if e["event"] == "cost_ceiling_exceeded"]

    def test_unknown_contribution_emits_unknown_once_no_abort(self, tmp_path: Path) -> None:
        _, events = _run(
            tmp_path, [_usage("claude-sonnet-5-5"), _usage("claude-haiku-4-5")], ceiling=0.01
        )
        unknown = [e for e in events if e["event"] == "cost_ceiling_unknown"]
        assert len(unknown) == 1
        assert unknown[0]["reason"] == "unpriceable model"
        assert not [e for e in events if e["event"] == "cost_ceiling_exceeded"]


class TestPricingDate:
    def test_cross_date_same_model_priced_individually(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setitem(
            pricing.INTRO_PRICING,
            "claude-haiku-4-5",
            {
                "expires": "2026-01-02",
                "input": 0.25,
                "output": 0.25,
                "cache_read": 0.0,
                "cache_creation": 0.0,
            },
        )
        probe_early = estimate_cost_usd("claude-haiku-4-5", M, 0, 0, 0, as_of=date(2026, 1, 1))
        probe_late = estimate_cost_usd("claude-haiku-4-5", M, 0, 0, 0, as_of=date(2026, 1, 3))
        assert probe_early != probe_late  # the patched boundary is effective
        for order in (False, True):
            events = [
                _usage("claude-haiku-4-5", observed_at="2026-01-01T23:30:00-05:00"),  # UTC Jan 2
                _usage("claude-haiku-4-5", observed_at="2026-01-03T00:00:00Z"),
            ]
            if order:
                events.reverse()
            sub = tmp_path / str(order)
            sub.mkdir()
            usage, _ = _run(sub, events)
            cost, _ = _state_cost(usage)
            first = estimate_cost_usd("claude-haiku-4-5", M, 0, 0, 0, as_of=date(2026, 1, 2))
            assert cost == pytest.approx(first + probe_late)

    def test_unparseable_time_uses_completion_date_fallback(self) -> None:
        (bucket,) = build_usage_contributions([_usage("claude-haiku-4-5", observed_at="garbage")])
        assert bucket["pricing_date"] is None


class TestAttributionCompatibility:
    def _row(self, **extra: Any) -> dict[str, Any]:
        return {
            "state": "work",
            "model": "claude-haiku-4-5",
            "input_tokens": M,
            "output_tokens": 0,
            "cache_read_tokens": 0,
            "cache_creation_tokens": 0,
            "timestamp": "2026-02-01T00:00:00Z",
            **extra,
        }

    def _report(self, tmp_path: Path, row: dict[str, Any]) -> Any:
        path = tmp_path / "usage.jsonl"
        path.write_text(json.dumps(row) + "\n")
        (state,) = CostReport.from_usage_jsonl(path).states
        return state

    def test_legacy_row_without_key_keeps_last_model_pricing(self, tmp_path: Path) -> None:
        assert self._report(tmp_path, self._row()).cost_usd == pytest.approx(1.0)

    @pytest.mark.parametrize("bad", [[], None, "x", [{"model": ""}], [42]])
    def test_invalid_new_attribution_is_unavailable(self, tmp_path: Path, bad: Any) -> None:
        state = self._report(tmp_path, self._row(usage_contributions=bad))
        assert state.cost_usd is None
        assert state.unavailable_reason == "invalid usage attribution"
        assert state.input_tokens == M
