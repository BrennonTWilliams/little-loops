"""Tests for /ll:analyze-loop Step 3b Semantic Synthesis structural conditions.

Validates fixture structure for sub-steps 3b-2 through 3b-5 without executing
any LLM calls. Modeled after TestReviewLoopSemanticChecks in test_review_loop.py:748.
"""

from __future__ import annotations

from pathlib import Path

import yaml

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "fsm"

# Decision-state prefixes from SKILL.md:230 (wider than SR-2's GATE_STATE_PREFIXES)
DECISION_PREFIXES = ("check_", "verify_", "evaluate_", "wait_")

# Dominant cycling threshold from SKILL.md:229
DOMINANT_CYCLING_THRESHOLD = 70.0

# Goal alignment dominant share threshold from SKILL.md:212
GOAL_ALIGNMENT_THRESHOLD = 50.0


class TestAnalyzeLoopSynthesis:
    def _load_fixture(self, name: str) -> dict:
        path = FIXTURES_DIR / name
        assert path.exists(), f"Fixture not found: {path}"
        with open(path) as f:
            return yaml.safe_load(f)

    def _happy_path(self, spec: dict) -> list[str]:
        states = spec.get("states", {})
        current = spec.get("initial")
        path: list[str] = []
        seen: set[str] = set()
        while current and current not in seen:
            path.append(current)
            seen.add(current)
            state = states.get(current, {})
            if state.get("terminal"):
                break
            current = state.get("on_yes") or state.get("next")
        return path

    # ------------------------------------------------------------------
    # 3b-2: Path reconstruction
    # ------------------------------------------------------------------

    def test_3b2_happy_path_reconstruction_multi_signal(self) -> None:
        spec = self._load_fixture("analysis-multi-signal.yaml")
        path = self._happy_path(spec)
        assert path == ["process_item", "validate_output", "done"]

    def test_3b2_happy_path_reconstruction_misaligned(self) -> None:
        spec = self._load_fixture("analysis-completed-misaligned.yaml")
        path = self._happy_path(spec)
        assert path == ["check_lint", "finalize", "done"]

    def test_3b2_happy_path_reconstruction_dominant_cycling(self) -> None:
        spec = self._load_fixture("analysis-dominant-cycling.yaml")
        path = self._happy_path(spec)
        assert path == ["check_build", "done"]

    # ------------------------------------------------------------------
    # 3b-3: Goal alignment
    # ------------------------------------------------------------------

    def test_3b3_misaligned_description_has_five_or_more_words(self) -> None:
        spec = self._load_fixture("analysis-completed-misaligned.yaml")
        description = spec.get("description", "")
        assert len(description.split()) >= 5

    def test_3b3_dominant_state_words_absent_from_description(self) -> None:
        spec = self._load_fixture("analysis-completed-misaligned.yaml")
        description = spec.get("description", "").lower()
        dominant = spec["initial"]  # check_lint
        dominant_words = set(dominant.replace("_", " ").split())
        desc_words = set(description.lower().split())
        assert not dominant_words.intersection(desc_words), (
            f"Dominant state words {dominant_words} overlap with description words — "
            "fixture must keep description unrelated to dominant state for 3b-3 to flag"
        )

    def test_3b3_dominant_state_cycles_to_itself(self) -> None:
        spec = self._load_fixture("analysis-completed-misaligned.yaml")
        states = spec["states"]
        dominant = spec["initial"]  # check_lint
        defn = states[dominant]
        cycles = (
            defn.get("on_yes") == dominant
            or defn.get("on_no") == dominant
            or defn.get("on_error") == dominant
        )
        assert cycles, f"Dominant state '{dominant}' must loop back to itself for cycling detection"

    def test_3b3_fixture_has_terminal_state(self) -> None:
        spec = self._load_fixture("analysis-completed-misaligned.yaml")
        terminal_states = [n for n, d in spec["states"].items() if d.get("terminal")]
        assert len(terminal_states) >= 1

    def test_3b3_inline_dominant_share_meets_threshold(self) -> None:
        # 6 visits to check_lint, 1 to finalize, 1 to done → 75% ≥ 50%
        visits = {"check_lint": 6, "finalize": 1, "done": 1}
        total = sum(visits.values())
        dominant = max(visits, key=visits.__getitem__)
        share = (visits[dominant] / total) * 100
        assert share >= GOAL_ALIGNMENT_THRESHOLD

    def test_3b3_inline_skipped_when_description_too_short(self) -> None:
        assert len("Run checks".split()) < 5

    # ------------------------------------------------------------------
    # 3b-4: Cross-signal grouping
    # ------------------------------------------------------------------

    def test_3b4_fixture_has_prompt_then_shell_adjacency(self) -> None:
        spec = self._load_fixture("analysis-multi-signal.yaml")
        states = spec["states"]
        assert states["process_item"]["action_type"] == "prompt"
        assert states["validate_output"]["action_type"] == "shell"

    def test_3b4_prompt_state_transitions_to_shell_state(self) -> None:
        spec = self._load_fixture("analysis-multi-signal.yaml")
        states = spec["states"]
        on_yes = states["process_item"].get("on_yes")
        assert on_yes == "validate_output", (
            "process_item must transition to validate_output via on_yes for adjacency"
        )

    def test_3b4_shell_state_has_evaluate_block(self) -> None:
        spec = self._load_fixture("analysis-multi-signal.yaml")
        states = spec["states"]
        assert "evaluate" in states["validate_output"], (
            "validate_output must have an evaluate block (shell state with evaluate failure)"
        )

    def test_3b4_inline_adjacency_defined_by_on_yes(self) -> None:
        # Structural definition: A→B is adjacent when A.on_yes == B
        spec = self._load_fixture("analysis-multi-signal.yaml")
        path = self._happy_path(spec)
        states = spec["states"]
        adjacent_pairs = [
            (path[i], path[i + 1])
            for i in range(len(path) - 1)
            if states.get(path[i], {}).get("on_yes") == path[i + 1]
        ]
        assert ("process_item", "validate_output") in adjacent_pairs

    # ------------------------------------------------------------------
    # 3b-5: Sub-threshold detection (dominant cycling)
    # ------------------------------------------------------------------

    def test_3b5_dominant_state_has_decision_prefix(self) -> None:
        spec = self._load_fixture("analysis-dominant-cycling.yaml")
        dominant = spec["initial"]  # check_build
        assert any(dominant.startswith(p) for p in DECISION_PREFIXES), (
            f"Dominant state '{dominant}' must match a decision prefix for 3b-5 to flag"
        )

    def test_3b5_dominant_state_loops_to_itself(self) -> None:
        spec = self._load_fixture("analysis-dominant-cycling.yaml")
        states = spec["states"]
        dominant = spec["initial"]  # check_build
        defn = states[dominant]
        loops_back = defn.get("on_no") == dominant or defn.get("on_error") == dominant
        assert loops_back, f"Dominant state '{dominant}' must loop back to itself"

    def test_3b5_fixture_has_more_than_one_state(self) -> None:
        spec = self._load_fixture("analysis-dominant-cycling.yaml")
        assert len(spec["states"]) > 1

    def test_3b5_inline_dominant_share_meets_threshold(self) -> None:
        # 7 visits to check_build, 1 to done → 87.5% ≥ 70%
        visits = {"check_build": 7, "done": 1}
        total = sum(visits.values())
        dominant = max(visits, key=visits.__getitem__)
        share = (visits[dominant] / total) * 100
        assert share >= DOMINANT_CYCLING_THRESHOLD

    def test_3b5_inline_below_threshold_no_flag(self) -> None:
        # 3 visits to check_build, 3 to done → 50% < 70%
        visits = {"check_build": 3, "done": 3}
        total = sum(visits.values())
        dominant = max(visits, key=visits.__getitem__)
        share = (visits[dominant] / total) * 100
        assert share < DOMINANT_CYCLING_THRESHOLD

    # ------------------------------------------------------------------
    # Step 3: Sub-loop verdict laundering signal
    # ------------------------------------------------------------------

    def test_subloop_laundering_has_sub_loop_state(self) -> None:
        """Laundering fixture must contain at least one state with a loop: key."""
        spec = self._load_fixture("assess-subloop-laundering.yaml")
        states = spec.get("states", {})
        sub_loop_states = [n for n, d in states.items() if "loop" in d]
        assert sub_loop_states
        # → analyze-loop should check on_yes == on_no for all sub-loop states

    def test_subloop_laundering_on_yes_equals_on_no(self) -> None:
        """Sub-loop state routes success and failure to the same next state."""
        spec = self._load_fixture("assess-subloop-laundering.yaml")
        states = spec.get("states", {})
        for name, defn in states.items():
            if "loop" in defn:
                assert defn.get("on_yes") == defn.get("on_no"), (
                    f"Sub-loop state '{name}' must have on_yes == on_no for laundering fixture"
                )
                # → analyze-loop should emit BUG — Sub-loop verdict discarded (P3)

    def test_subloop_laundering_shared_next_state_exists(self) -> None:
        """The shared destination state that both on_yes and on_no route to actually exists."""
        spec = self._load_fixture("assess-subloop-laundering.yaml")
        states = spec.get("states", {})
        initial = spec.get("initial")
        sub_loop_state = states.get(initial, {})
        assert "loop" in sub_loop_state
        next_state = sub_loop_state.get("on_yes")
        assert next_state is not None
        assert next_state in states
        # → child verdict silently discarded; signal title includes shared_next

    def test_subloop_laundering_happy_path_reaches_terminal(self) -> None:
        """Happy-path traversal completes normally despite laundering defect."""
        spec = self._load_fixture("assess-subloop-laundering.yaml")
        path = self._happy_path(spec)
        states = spec.get("states", {})
        assert states.get(path[-1], {}).get("terminal") is True
        # → loop appears to succeed; laundering only detected via FSM structure inspection
