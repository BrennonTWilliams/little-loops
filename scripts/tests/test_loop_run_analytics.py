"""Tests for little_loops.analytics.variance module."""

from __future__ import annotations

from pathlib import Path

import pytest  # noqa: F401 — pytest fixture discovery

from little_loops.analytics.variance import (
    EvaluatorVariance,
    VarianceReport,
    _correlate_verdicts,
    _generate_recommendation,
    compute_evaluator_variance,
)


class TestEvaluatorVariance:
    """Tests for EvaluatorVariance dataclass."""

    def test_to_dict_basic(self) -> None:
        """to_dict includes all fields."""
        ev = EvaluatorVariance(
            state="check_semantic",
            evaluator_type="llm_structured",
            pass_count=45,
            total=50,
            pass_rate=0.9,
            variance=0.09,
        )
        d = ev.to_dict()
        assert d["state"] == "check_semantic"
        assert d["evaluator_type"] == "llm_structured"
        assert d["pass_count"] == 45
        assert d["total"] == 50
        assert d["pass_rate"] == 0.9
        assert d["variance"] == 0.09
        assert "recommendation" not in d

    def test_to_dict_with_recommendation(self) -> None:
        """to_dict includes recommendation when present."""
        ev = EvaluatorVariance(
            state="check",
            evaluator_type="exit_code",
            pass_count=10,
            total=10,
            pass_rate=1.0,
            variance=0.0,
            recommendation="Command may not exercise the feature.",
        )
        d = ev.to_dict()
        assert d["recommendation"] == "Command may not exercise the feature."


class TestVarianceReport:
    """Tests for VarianceReport dataclass."""

    def test_to_dict_empty_states(self) -> None:
        """to_dict with no states."""
        report = VarianceReport(loop="test-loop", total_runs=10)
        d = report.to_dict()
        assert d["loop"] == "test-loop"
        assert d["total_runs"] == 10
        assert d["states"] == []

    def test_to_dict_with_states(self) -> None:
        """to_dict includes state dicts."""
        ev = EvaluatorVariance(
            state="check",
            evaluator_type="exit_code",
            pass_count=5,
            total=5,
            pass_rate=1.0,
            variance=0.0,
        )
        report = VarianceReport(loop="test-loop", total_runs=10, states=[ev])
        d = report.to_dict()
        assert len(d["states"]) == 1
        assert d["states"][0]["state"] == "check"


class TestCorrelateVerdicts:
    """Tests for _correlate_verdicts()."""

    def test_basic_correlation(self) -> None:
        """Pairs evaluate events with preceding state_enter."""
        events = [
            {"event": "state_enter", "state": "check_semantic", "iteration": 1},
            {"event": "evaluate", "verdict": "yes"},
            {"event": "state_enter", "state": "check", "iteration": 1},
            {"event": "evaluate", "verdict": "no"},
        ]
        result = _correlate_verdicts(events)
        assert result == {"check_semantic": [True], "check": [False]}

    def test_multiple_verdicts_per_state(self) -> None:
        """Same state can have multiple evaluate events."""
        events = [
            {"event": "state_enter", "state": "check", "iteration": 1},
            {"event": "evaluate", "verdict": "yes"},
            {"event": "state_enter", "state": "check", "iteration": 2},
            {"event": "evaluate", "verdict": "no"},
        ]
        result = _correlate_verdicts(events)
        assert result == {"check": [True, False]}

    def test_evaluate_before_state_enter_ignored(self) -> None:
        """Evaluate events before any state_enter are ignored."""
        events = [
            {"event": "evaluate", "verdict": "yes"},
            {"event": "state_enter", "state": "check", "iteration": 1},
            {"event": "evaluate", "verdict": "no"},
        ]
        result = _correlate_verdicts(events)
        assert result == {"check": [False]}

    def test_yes_self_assessed_is_true(self) -> None:
        """yes (self-assessed) maps to True."""
        events = [
            {"event": "state_enter", "state": "check", "iteration": 1},
            {"event": "evaluate", "verdict": "yes (self-assessed)"},
        ]
        result = _correlate_verdicts(events)
        assert result == {"check": [True]}

    def test_progress_is_true(self) -> None:
        """progress verdict maps to True."""
        events = [
            {"event": "state_enter", "state": "check", "iteration": 1},
            {"event": "evaluate", "verdict": "progress"},
        ]
        result = _correlate_verdicts(events)
        assert result == {"check": [True]}

    def test_success_is_true(self) -> None:
        """success verdict maps to True."""
        events = [
            {"event": "state_enter", "state": "check", "iteration": 1},
            {"event": "evaluate", "verdict": "success"},
        ]
        result = _correlate_verdicts(events)
        assert result == {"check": [True]}

    def test_empty_events(self) -> None:
        """Empty events list returns empty dict."""
        result = _correlate_verdicts([])
        assert result == {}


class TestGenerateRecommendation:
    """Tests for _generate_recommendation()."""

    def test_no_recommendation_for_high_variance(self) -> None:
        """Variance > 0.05 returns None."""
        result = _generate_recommendation("check", "llm_structured", pass_rate=0.5, variance=0.25)
        assert result is None

    def test_llm_structured_high_pass(self) -> None:
        """High pass rate + llm_structured generates prompt-broadening recommendation."""
        result = _generate_recommendation(
            "check_semantic",
            "llm_structured",
            pass_rate=0.98,
            variance=0.02,
            prompt="Did the issue file get updated with new codebase references?",
        )
        assert result is not None
        assert "judge prompt" in result
        assert "tighten to require specific evidence" in result
        assert "Did the issue file get updated" in result

    def test_llm_structured_no_prompt(self) -> None:
        """llm_structured without prompt still gets recommendation."""
        result = _generate_recommendation("check", "llm_structured", pass_rate=0.96, variance=0.04)
        assert result is not None
        assert "may be too broad" in result

    def test_output_numeric_100_percent_pass(self) -> None:
        """100% pass + output_numeric generates target-looseness recommendation."""
        result = _generate_recommendation(
            "check_invariants",
            "output_numeric",
            pass_rate=1.0,
            variance=0.0,
            target=50,
        )
        assert result is not None
        assert "target=50" in result
        assert "Target may be too loose" in result

    def test_exit_code_99_percent_pass(self) -> None:
        """99% pass + exit_code generates command-not-exercising recommendation."""
        result = _generate_recommendation("check", "exit_code", pass_rate=0.99, variance=0.0099)
        assert result is not None
        assert "Command may not exercise the feature" in result

    def test_exit_code_perfect_pass(self) -> None:
        """Perfect pass + exit_code flagged."""
        result = _generate_recommendation("check", "exit_code", pass_rate=1.0, variance=0.0)
        assert result is not None
        assert "Command may not exercise the feature" in result


class TestComputeEvaluatorVariance:
    """Tests for compute_evaluator_variance()."""

    def _make_events_jsonl(self, run_dir: Path, events: list[dict]) -> None:
        """Write synthetic events.jsonl."""
        import json

        run_dir.mkdir(parents=True, exist_ok=True)
        with open(run_dir / "events.jsonl", "w") as f:
            for event in events:
                f.write(json.dumps(event) + "\n")

    def test_no_history_returns_none(self, tmp_path: Path) -> None:
        """Returns None when no .history directory."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        result = compute_evaluator_variance("my-loop", loops_dir)
        assert result is None

    def test_insufficient_runs_returns_none(self, tmp_path: Path) -> None:
        """Returns None when run count < min_runs."""
        loops_dir = tmp_path / ".loops"
        history_root = loops_dir / ".history"
        run_dir = history_root / "20260101T000000-my-loop"
        events = [
            {"event": "state_enter", "state": "check", "iteration": 1},
            {"event": "evaluate", "verdict": "yes"},
        ]
        self._make_events_jsonl(run_dir, events)

        result = compute_evaluator_variance("my-loop", loops_dir, min_runs=10)
        assert result is None

    def test_all_pass_zero_variance(self, tmp_path: Path) -> None:
        """All-pass evaluator has variance 0."""
        loops_dir = tmp_path / ".loops"
        history_root = loops_dir / ".history"

        for i in range(10):
            run_dir = history_root / f"20260101T0000{i:02d}-my-loop"
            events = [
                {"event": "state_enter", "state": "check", "iteration": 1},
                {"event": "evaluate", "verdict": "yes"},
            ]
            self._make_events_jsonl(run_dir, events)

        result = compute_evaluator_variance("my-loop", loops_dir, min_runs=10)
        assert result is not None
        assert result.total_runs == 10
        assert len(result.states) == 1
        assert result.states[0].state == "check"
        assert result.states[0].pass_rate == 1.0
        assert result.states[0].variance == 0.0

    def test_all_fail_zero_variance(self, tmp_path: Path) -> None:
        """All-fail evaluator has variance 0."""
        loops_dir = tmp_path / ".loops"
        history_root = loops_dir / ".history"

        for i in range(10):
            run_dir = history_root / f"20260101T0000{i:02d}-my-loop"
            events = [
                {"event": "state_enter", "state": "check", "iteration": 1},
                {"event": "evaluate", "verdict": "no"},
            ]
            self._make_events_jsonl(run_dir, events)

        result = compute_evaluator_variance("my-loop", loops_dir, min_runs=10)
        assert result is not None
        assert result.states[0].pass_rate == 0.0
        assert result.states[0].variance == 0.0

    def test_mixed_50_50(self, tmp_path: Path) -> None:
        """50/50 verdicts have variance 0.25."""
        loops_dir = tmp_path / ".loops"
        history_root = loops_dir / ".history"

        verdicts = ["yes", "no"] * 5
        for i, verdict in enumerate(verdicts):
            run_dir = history_root / f"20260101T0000{i:02d}-my-loop"
            events = [
                {"event": "state_enter", "state": "check", "iteration": 1},
                {"event": "evaluate", "verdict": verdict},
            ]
            self._make_events_jsonl(run_dir, events)

        result = compute_evaluator_variance("my-loop", loops_dir, min_runs=10)
        assert result is not None
        assert result.states[0].pass_rate == 0.5
        assert result.states[0].variance == 0.25

    def test_states_sorted_by_variance_ascending(self, tmp_path: Path) -> None:
        """States sorted by variance (lowest variance first)."""
        loops_dir = tmp_path / ".loops"
        history_root = loops_dir / ".history"

        for i in range(10):
            run_dir = history_root / f"20260101T0000{i:02d}-my-loop"
            events = [
                {"event": "state_enter", "state": "always_yes", "iteration": 1},
                {"event": "evaluate", "verdict": "yes"},
                {"event": "state_enter", "state": "mixed", "iteration": 1},
                {"event": "evaluate", "verdict": "yes" if i < 5 else "no"},
            ]
            self._make_events_jsonl(run_dir, events)

        result = compute_evaluator_variance("my-loop", loops_dir, min_runs=10)
        assert result is not None
        assert len(result.states) == 2
        # always_yes should be first (variance=0)
        assert result.states[0].state == "always_yes"
        assert result.states[0].variance == 0.0
        # mixed should be second (variance=0.25)
        assert result.states[1].state == "mixed"
        assert result.states[1].variance == 0.25


class TestEvaluatorVarianceWilsonCI:
    """Wilson CI is computed and stored on EvaluatorVariance (ENH-2084)."""

    def _make_events_jsonl(self, run_dir: Path, events: list[dict]) -> None:
        import json

        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "events.jsonl").write_text("\n".join(json.dumps(e) for e in events) + "\n")

    def test_evaluator_variance_has_ci_field(self) -> None:
        """EvaluatorVariance dataclass has a ci attribute."""
        ev = EvaluatorVariance(
            state="check",
            evaluator_type="exit_code",
            pass_count=5,
            total=10,
            pass_rate=0.5,
            variance=0.25,
        )
        assert hasattr(ev, "ci")

    def test_ci_populated_by_compute(self, tmp_path: Path) -> None:
        """compute_evaluator_variance populates ci on each state."""
        loops_dir = tmp_path / ".loops"
        history_root = loops_dir / ".history"

        for i in range(10):
            run_dir = history_root / f"20260101T0000{i:02d}-my-loop"
            events = [
                {"event": "state_enter", "state": "check", "iteration": 1},
                {"event": "evaluate", "verdict": "yes" if i < 7 else "no"},
            ]
            self._make_events_jsonl(run_dir, events)

        result = compute_evaluator_variance("my-loop", loops_dir, min_runs=10)
        assert result is not None
        state = result.states[0]
        assert state.ci is not None
        lo, hi = state.ci
        assert 0.0 <= lo <= 1.0
        assert 0.0 <= hi <= 1.0
        assert lo <= hi
        # k=7, n=10: lo ≈ 0.397, hi ≈ 0.892
        assert lo == pytest.approx(0.397, abs=0.01)
        assert hi == pytest.approx(0.892, abs=0.01)

    def test_ci_in_to_dict(self, tmp_path: Path) -> None:
        """to_dict() includes ci bounds when present."""
        ev = EvaluatorVariance(
            state="check",
            evaluator_type="exit_code",
            pass_count=7,
            total=10,
            pass_rate=0.7,
            variance=0.21,
            ci=(0.397, 0.892),
        )
        d = ev.to_dict()
        assert "ci_lower" in d
        assert "ci_upper" in d
        assert d["ci_lower"] == pytest.approx(0.397)
        assert d["ci_upper"] == pytest.approx(0.892)
