"""Tests for BUG-2752: check_guard2_verdict regex misses real issue-size-review output.

The guard-2 "Very Large" skip line is freeform agent-generated prose (no fixed
template in skills/issue-size-review/SKILL.md for the 8-11 range), so
``check_guard2_verdict``'s pattern must tolerate arbitrary text between
"skipped:" and "score N", and ``check_guard2_score_fallback`` must catch any
remaining drift by probing for a bare "score N" substring.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from little_loops.fsm.evaluators import evaluate_output_contains

AUTODEV_LOOP_PATH = Path(__file__).parent.parent / "little_loops" / "loops" / "autodev.yaml"


def _load_autodev_yaml() -> dict[str, Any]:
    assert AUTODEV_LOOP_PATH.exists(), f"Loop file not found: {AUTODEV_LOOP_PATH}"
    return yaml.safe_load(AUTODEV_LOOP_PATH.read_text())


def _pattern(states: dict[str, Any], state_name: str) -> str:
    state = states[state_name]
    return str(state["evaluate"]["pattern"])


REAL_FEAT_021_OUTPUT = (
    "FEAT-021 skipped: score 11 (Very Large) — strictly sequential, "
    "shared-infra children"
)


class TestCheckGuard2VerdictPattern:
    def test_guard2_pattern_matches_status_line(self) -> None:
        states = _load_autodev_yaml()["states"]
        pattern = _pattern(states, "check_guard2_verdict")

        result = evaluate_output_contains(REAL_FEAT_021_OUTPUT, pattern)

        assert result.verdict == "yes"

    def test_guard2_pattern_still_matches_exact_prefix_shape(self) -> None:
        states = _load_autodev_yaml()["states"]
        pattern = _pattern(states, "check_guard2_verdict")

        result = evaluate_output_contains("skipped: score 8 ", pattern)

        assert result.verdict == "yes"

    def test_guard2_pattern_rejects_guard1_ambiguous_line(self) -> None:
        states = _load_autodev_yaml()["states"]
        pattern = _pattern(states, "check_guard2_verdict")

        result = evaluate_output_contains(
            "skipped: structural score 6 but outcome_confidence low is qualitative",
            pattern,
        )

        assert result.verdict == "no"

    def test_guard2_pattern_rejects_out_of_range_score(self) -> None:
        states = _load_autodev_yaml()["states"]
        pattern = _pattern(states, "check_guard2_verdict")

        result = evaluate_output_contains("skipped: score 5 (ambiguous)", pattern)

        assert result.verdict == "no"

    def test_guard2_verdict_routes_on_no_to_fallback_state(self) -> None:
        states = _load_autodev_yaml()["states"]
        state = states["check_guard2_verdict"]

        assert state["on_no"] == "check_guard2_score_fallback"
        assert state["on_yes"] == "check_readiness_for_atomic_remediation"


class TestCheckGuard2ScoreFallback:
    def test_guard2_fallback_probe_detects_score_9(self) -> None:
        states = _load_autodev_yaml()["states"]
        pattern = _pattern(states, "check_guard2_score_fallback")

        result = evaluate_output_contains(
            "FEAT-099 declined decomposition: score 9 way too tangled to split",
            pattern,
        )

        assert result.verdict == "yes"

    def test_guard2_fallback_probe_rejects_out_of_range_score(self) -> None:
        states = _load_autodev_yaml()["states"]
        pattern = _pattern(states, "check_guard2_score_fallback")

        result = evaluate_output_contains("looks fine, score 3, no action needed", pattern)

        assert result.verdict == "no"

    def test_guard2_fallback_routes_to_readiness_or_recheck(self) -> None:
        states = _load_autodev_yaml()["states"]
        state = states["check_guard2_score_fallback"]

        assert state["on_yes"] == "check_readiness_for_atomic_remediation"
        assert state["on_no"] == "recheck_after_size_review"

    def test_guard2_fallback_uses_evaluate_source_not_shell_action(self) -> None:
        """BUG-2594: never shell-interpolate untrusted captured text."""
        states = _load_autodev_yaml()["states"]
        state = states["check_guard2_score_fallback"]

        assert "action" not in state
        assert state["evaluate"]["source"] == "${captured.size_review_output.output}"
