"""Non-discriminating evaluator detection from run history."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class EvaluatorVariance:
    """Variance analysis for a single evaluator state.

    Attributes:
        state: State name.
        evaluator_type: Evaluator type (e.g. llm_structured, exit_code).
        pass_count: Number of positive verdicts.
        total: Total number of evaluate events for this state.
        pass_rate: pass_count / total (0.0 if total == 0).
        variance: Bernoulli variance p*(1-p).
        recommendation: Human-readable recommendation if variance is low, else None.
    """

    state: str
    evaluator_type: str
    pass_count: int
    total: int
    pass_rate: float
    variance: float
    recommendation: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result: dict[str, Any] = {
            "state": self.state,
            "evaluator_type": self.evaluator_type,
            "pass_count": self.pass_count,
            "total": self.total,
            "pass_rate": round(self.pass_rate, 4),
            "variance": round(self.variance, 4),
        }
        if self.recommendation:
            result["recommendation"] = self.recommendation
        return result


@dataclass
class VarianceReport:
    """Full variance report for a loop.

    Attributes:
        loop: Loop name.
        total_runs: Number of runs analyzed.
        states: Per-state variance results, sorted by variance ascending.
    """

    loop: str
    total_runs: int
    states: list[EvaluatorVariance] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "loop": self.loop,
            "total_runs": self.total_runs,
            "states": [s.to_dict() for s in self.states],
        }


def _correlate_verdicts(
    events: list[dict[str, Any]],
) -> dict[str, list[bool]]:
    """Correlate evaluate events with state_enter events to get per-state verdicts.

    Walks events chronologically, tracking current state from state_enter
    events, then pairs each evaluate event with the tracked state.

    Args:
        events: List of event dicts from events.jsonl.

    Returns:
        Dict mapping state name to list of bool verdicts (True = positive).
    """
    from little_loops.fsm.persistence import _verdict_is_yes

    state_verdicts: dict[str, list[bool]] = {}
    current_state: str | None = None

    for event in events:
        if event.get("event") == "state_enter":
            current_state = event.get("state")
        elif event.get("event") == "evaluate" and current_state:
            verdict_str = event.get("verdict", "")
            state_verdicts.setdefault(current_state, []).append(
                _verdict_is_yes(verdict_str)
            )

    return state_verdicts


def _generate_recommendation(
    state: str,
    evaluator_type: str,
    pass_rate: float,
    variance: float,
    prompt: str | None = None,
    target: Any = None,
) -> str | None:
    """Generate a recommendation for a low-variance evaluator.

    Pattern-matches common failure modes:
    - High pass-rate + llm_structured → "broaden judge criteria"
    - 100% pass + output_numeric → "target may be too loose"
    - 100% pass + exit_code → "command may not exercise the feature"

    Args:
        state: State name.
        evaluator_type: Evaluator type string.
        pass_rate: Observed pass rate.
        variance: Bernoulli variance.
        prompt: Evaluator prompt (for llm_structured).
        target: Target value (for output_numeric).

    Returns:
        Recommendation string or None if evaluator appears discriminating.
    """
    if variance > 0.05:
        return None

    if pass_rate >= 0.95 and evaluator_type == "llm_structured":
        prompt_preview = ""
        if prompt:
            truncated = prompt[:100] + "..." if len(prompt) > 100 else prompt
            prompt_preview = f"\n  ↳ judge prompt: \"{truncated}\""
        return (
            f"Judge prompt may be too broad — most inputs pass trivially.{prompt_preview}\n"
            f"  Recommendation: tighten to require specific evidence "
            f"(e.g., confidence_score increase, new codebase references added)."
        )

    if pass_rate >= 0.99 and evaluator_type == "output_numeric":
        target_str = f" (target={target})" if target is not None else ""
        return (
            f"Target may be too loose for actual output values{target_str}.\n"
            f"  Recommendation: lower the target or inspect typical run outputs "
            f"to find a more discriminating threshold."
        )

    if pass_rate >= 0.99 and evaluator_type == "exit_code":
        return (
            "Command may not exercise the feature — exits 0 regardless of intent.\n"
            "  Recommendation: replace with a command that fails on meaningful "
            "conditions (e.g., grep for expected output, diff against baseline)."
        )

    return None


def compute_evaluator_variance(
    loop_name: str,
    loops_dir: Path,
    threshold: float = 0.05,
    min_runs: int = 10,
) -> VarianceReport | None:
    """Compute per-state evaluator variance from run history.

    Walks .loops/.history/*-{loop_name}/events.jsonl, correlates evaluate
    events with state_enter events, computes Bernoulli variance p*(1-p)
    per state, and generates recommendations for low-variance evaluators.

    Args:
        loop_name: Name of the loop to analyze.
        loops_dir: Base directory containing .loops/.
        threshold: Variance floor below which a state is flagged (default 0.05).
        min_runs: Minimum runs required to compute meaningful variance (default 10).

    Returns:
        VarianceReport if history exists and min_runs is met, None otherwise.
    """
    from little_loops.fsm.persistence import HISTORY_DIR

    history_root = loops_dir / HISTORY_DIR
    if not history_root.exists():
        return None

    suffix = f"-{loop_name}"
    all_verdicts: dict[str, list[bool]] = {}
    run_count = 0

    for run_dir in sorted(history_root.iterdir(), key=lambda d: d.name):
        if not run_dir.is_dir() or not run_dir.name.endswith(suffix):
            continue
        events_file = run_dir / "events.jsonl"
        if not events_file.exists():
            continue
        import json as _json

        events: list[dict[str, Any]] = []
        try:
            for line in events_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    try:
                        events.append(_json.loads(line))
                    except _json.JSONDecodeError:
                        pass
        except OSError:
            continue

        run_verdicts = _correlate_verdicts(events)
        for state, verdicts in run_verdicts.items():
            all_verdicts.setdefault(state, []).extend(verdicts)
        run_count += 1

    if run_count < min_runs:
        return None

    # Load loop YAML to get evaluator configs
    evaluator_configs: dict[str, dict[str, Any]] = {}
    try:
        from little_loops.cli.loop._helpers import load_loop
        from little_loops.logger import Logger

        fsm = load_loop(loop_name, loops_dir, Logger(verbose=False))
        for name, state in fsm.states.items():
            if state.evaluate is not None:
                evaluator_configs[name] = {
                    "type": state.evaluate.type,
                    "prompt": state.evaluate.prompt,
                    "target": state.evaluate.target,
                }
    except (FileNotFoundError, ValueError):
        pass

    states: list[EvaluatorVariance] = []
    for state_name in sorted(all_verdicts.keys()):
        verdicts = all_verdicts[state_name]
        total = len(verdicts)
        if total == 0:
            continue
        pass_count = sum(1 for v in verdicts if v)
        pass_rate = pass_count / total
        variance = pass_rate * (1 - pass_rate)

        config = evaluator_configs.get(state_name, {})
        eval_type = config.get("type", "unknown")
        recommendation = _generate_recommendation(
            state_name,
            eval_type,
            pass_rate,
            variance,
            prompt=config.get("prompt"),
            target=config.get("target"),
        )

        states.append(
            EvaluatorVariance(
                state=state_name,
                evaluator_type=eval_type,
                pass_count=pass_count,
                total=total,
                pass_rate=pass_rate,
                variance=variance,
                recommendation=recommendation,
            )
        )

    # Sort by variance ascending (lowest variance first — most suspicious)
    states.sort(key=lambda s: s.variance)

    return VarianceReport(
        loop=loop_name,
        total_runs=run_count,
        states=states,
    )
