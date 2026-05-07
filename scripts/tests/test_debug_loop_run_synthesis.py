"""Tests for /ll:debug-loop-run Step 3b Semantic Synthesis structural conditions.

Validates fixture structure for sub-steps 3b-2 through 3b-5 without executing
any LLM calls. Modeled after TestReviewLoopSemanticChecks in test_review_loop.py:748.
"""

from __future__ import annotations

from pathlib import Path

import yaml

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "fsm"

# Decision-state prefixes from SKILL.md:230 (wider than SR-2's GATE_STATE_PREFIXES)
DECISION_PREFIXES = ("check_", "verify_", "evaluate_", "wait_")

# Apply/refine-state prefixes for Signal 1 (iter-1 convergence without apply)
APPLY_STATE_PREFIXES = ("apply_", "refine_", "update_", "write_", "commit_")

# Dominant cycling threshold from SKILL.md:229
DOMINANT_CYCLING_THRESHOLD = 70.0

# Goal alignment dominant share threshold from SKILL.md:212
GOAL_ALIGNMENT_THRESHOLD = 50.0

# Signal 2 degenerate-gate threshold (per SKILL.md Step 3 Signal Rules)
DEGENERATE_GATE_THRESHOLD = 95.0
DEGENERATE_GATE_MIN_EVALS = 10


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
        # → debug-loop-run should check on_yes == on_no for all sub-loop states

    def test_subloop_laundering_on_yes_equals_on_no(self) -> None:
        """Sub-loop state routes success and failure to the same next state."""
        spec = self._load_fixture("assess-subloop-laundering.yaml")
        states = spec.get("states", {})
        for name, defn in states.items():
            if "loop" in defn:
                assert defn.get("on_yes") == defn.get("on_no"), (
                    f"Sub-loop state '{name}' must have on_yes == on_no for laundering fixture"
                )
                # → debug-loop-run should emit BUG — Sub-loop verdict discarded (P3)

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

    # ------------------------------------------------------------------
    # Step 3 ENH — Signal 1: Iteration-1 convergence without apply
    # ------------------------------------------------------------------

    def test_signal1_fixture_has_no_apply_state(self) -> None:
        """Signal 1 fixture must contain no apply/refine/update/write/commit state."""
        spec = self._load_fixture("analysis-iter1-no-apply.yaml")
        states = spec.get("states", {})
        apply_states = [n for n in states if any(n.startswith(p) for p in APPLY_STATE_PREFIXES)]
        assert not apply_states, (
            f"Signal 1 fixture must omit apply-prefixed states; found {apply_states}"
        )
        # → debug-loop-run should emit Signal 1 when iterations==1 and no apply state visited

    def test_signal1_fixture_initial_state_routes_yes_to_terminal(self) -> None:
        """Signal 1 trigger requires the initial evaluate state to exit on_yes -> terminal."""
        spec = self._load_fixture("analysis-iter1-no-apply.yaml")
        states = spec["states"]
        initial = spec["initial"]
        on_yes = states[initial].get("on_yes")
        assert on_yes is not None
        assert states.get(on_yes, {}).get("terminal") is True, (
            f"Initial state '{initial}' must route on_yes to a terminal state for iter-1 convergence"
        )

    def test_signal1_fixture_initial_state_has_decision_prefix(self) -> None:
        """Signal 1 typically fires on a check_/verify_/evaluate_/wait_ gate state."""
        spec = self._load_fixture("analysis-iter1-no-apply.yaml")
        initial = spec["initial"]
        # 'route_*' is the apo-textgrad real-world example; allow either decision-prefix
        # or 'route_' which is the canonical iter-1-convergence gate name in the wild
        assert any(initial.startswith(p) for p in DECISION_PREFIXES) or initial.startswith(
            "route_"
        ), f"Initial state '{initial}' should be a gate/decision state for Signal 1"

    def test_signal1_apply_prefix_constant_shape_matches_decision_prefix(self) -> None:
        """APPLY_STATE_PREFIXES is a tuple parallel to DECISION_PREFIXES — same convention."""
        assert isinstance(APPLY_STATE_PREFIXES, tuple)
        assert all(isinstance(p, str) and p.endswith("_") for p in APPLY_STATE_PREFIXES)
        assert APPLY_STATE_PREFIXES == ("apply_", "refine_", "update_", "write_", "commit_")

    # ------------------------------------------------------------------
    # Step 3 ENH — Signal 2: Degenerate gate route distribution
    # ------------------------------------------------------------------

    def test_signal2_fixture_initial_state_loops_to_self_on_no(self) -> None:
        """Degenerate gate: evaluate state with on_no routing back to itself produces
        an overwhelming single-branch route distribution."""
        spec = self._load_fixture("analysis-degenerate-gate.yaml")
        states = spec["states"]
        initial = spec["initial"]
        defn = states[initial]
        assert defn.get("on_no") == initial, (
            f"Signal 2 fixture must route '{initial}' on_no back to itself"
        )

    def test_signal2_fixture_has_evaluate_block(self) -> None:
        """Signal 2 only applies to evaluate states (route events come from evaluate)."""
        spec = self._load_fixture("analysis-degenerate-gate.yaml")
        states = spec["states"]
        initial = spec["initial"]
        assert "evaluate" in states[initial], (
            f"Signal 2 fixture state '{initial}' must have an evaluate block"
        )

    def test_signal2_inline_degenerate_threshold_meets(self) -> None:
        """10 evaluations all routing to one branch -> 100% > 95% threshold."""
        # {from_state: {to_state: count}} — debug-loop-run walker's accumulator shape
        route_distribution = {"check_outcome": {"check_outcome": 10}}
        from_state = "check_outcome"
        branches = route_distribution[from_state]
        total = sum(branches.values())
        assert total >= DEGENERATE_GATE_MIN_EVALS
        dominant_count = max(branches.values())
        share = (dominant_count / total) * 100
        assert share > DEGENERATE_GATE_THRESHOLD

    def test_signal2_inline_below_threshold_no_flag(self) -> None:
        """6 of 10 to one branch -> 60% < 95%, no signal."""
        route_distribution = {"check_outcome": {"check_outcome": 6, "done": 4}}
        from_state = "check_outcome"
        branches = route_distribution[from_state]
        total = sum(branches.values())
        dominant_count = max(branches.values())
        share = (dominant_count / total) * 100
        assert share < DEGENERATE_GATE_THRESHOLD

    def test_signal2_inline_below_min_evals_no_flag(self) -> None:
        """9 evaluations all to one branch but < 10 min — do not flag yet."""
        route_distribution = {"check_outcome": {"check_outcome": 9}}
        from_state = "check_outcome"
        branches = route_distribution[from_state]
        total = sum(branches.values())
        assert total < DEGENERATE_GATE_MIN_EVALS

    # ------------------------------------------------------------------
    # Step 2 static pass — Signal 3: Stub action detection
    # ------------------------------------------------------------------

    def test_signal3_fixture_score_state_has_numeric_echo_stub(self) -> None:
        """Signal 3 trigger pattern 1: echo "<digit>" in a score/evaluate/judge/reward state."""
        import re

        spec = self._load_fixture("analysis-stub-action.yaml")
        states = spec["states"]
        # Fixture's stub state name must contain one of the trigger keywords
        stub_state_keywords = ("score", "evaluate", "judge", "reward")
        stub_states = [n for n in states if any(kw in n for kw in stub_state_keywords)]
        assert stub_states, (
            f"Signal 3 fixture must include a state with name containing one of "
            f"{stub_state_keywords}"
        )
        # The stub state's action must match the numeric-echo regex from SKILL.md
        for name in stub_states:
            action = states[name].get("action", "")
            if re.match(r'^echo "\d+"$', action):
                return  # at least one stub matches
        raise AssertionError(
            f"None of the score-prefixed states had a matching stub-action body; "
            f"checked: {[states[n].get('action') for n in stub_states]}"
        )

    def test_signal3_inline_numeric_echo_pattern_matches(self) -> None:
        """Regex pattern 1: ^echo "\\d+"$ matches numeric verdicts."""
        import re

        pattern = re.compile(r'^echo "\d+"$')
        assert pattern.match('echo "5"')
        assert pattern.match('echo "42"')
        assert not pattern.match('echo "hello"')
        assert not pattern.match("echo 5")  # missing quotes

    def test_signal3_inline_replace_todo_echo_pattern_matches(self) -> None:
        """Regex pattern 2: ^echo "(Replace|TODO).*"$ matches placeholder text."""
        import re

        pattern_replace = re.compile(r'^echo "Replace.*"$')
        pattern_todo = re.compile(r'^echo "TODO.*"$')
        assert pattern_replace.match('echo "Replace this with a real action"')
        assert pattern_todo.match('echo "TODO: implement scoring"')
        assert not pattern_replace.match('echo "real work happens here"')

    def test_signal3_inline_uppercase_verdict_pattern_matches(self) -> None:
        """Regex pattern 3: ^echo "[A-Z_]+"$ matches literal verdict echoes."""
        import re

        pattern = re.compile(r'^echo "[A-Z_]+"$')
        assert pattern.match('echo "PASS"')
        assert pattern.match('echo "FAIL_RETRY"')
        assert not pattern.match('echo "pass"')  # lowercase
        assert not pattern.match('echo "Mixed_Case"')

    def test_signal3_fixture_score_state_routes_yes_to_terminal(self) -> None:
        """Stub-action fixture's score state should be a gate that exits on_yes -> done,
        modeling rl-rlhf.yaml::score behavior."""
        spec = self._load_fixture("analysis-stub-action.yaml")
        states = spec["states"]
        score_states = [n for n in states if "score" in n]
        assert score_states, "Fixture must contain a 'score' state"
        score = score_states[0]
        on_yes = states[score].get("on_yes")
        assert on_yes is not None
        assert states.get(on_yes, {}).get("terminal") is True or on_yes == "done"

    # ------------------------------------------------------------------
    # Step 3 ENH — Signal 4: Capture Vacuum
    # ------------------------------------------------------------------

    def test_signal4_fixture_has_producer_state_with_capture(self) -> None:
        """Signal 4 fixture must include at least one state with a `capture:` key
        (the producer whose output_preview is checked for emptiness)."""
        spec = self._load_fixture("analysis-capture-vacuum.yaml")
        states = spec.get("states", {})
        producers = [n for n, d in states.items() if "capture" in d]
        assert producers, "Signal 4 fixture must include a producer state with a 'capture:' key"

    def test_signal4_fixture_has_consumer_referencing_capture(self) -> None:
        """Signal 4 fixture must include a consumer state whose action references
        ${captured.X.output} — that's the trigger for the vacuum signal."""
        import re

        spec = self._load_fixture("analysis-capture-vacuum.yaml")
        states = spec.get("states", {})
        capture_ref = re.compile(r"\$\{captured\.\w+\.output\}")
        consumers = [n for n, d in states.items() if capture_ref.search(d.get("action", ""))]
        assert consumers, (
            "Signal 4 fixture must include a consumer state whose action references "
            "${captured.X.output}"
        )

    def test_signal4_consumer_reference_matches_producer_capture(self) -> None:
        """The consumer's ${captured.X.output} reference must name an actual
        capture in the fixture — otherwise Signal 4's join is structurally invalid."""
        import re

        spec = self._load_fixture("analysis-capture-vacuum.yaml")
        states = spec.get("states", {})
        producer_captures = {d["capture"] for d in states.values() if "capture" in d}
        capture_ref = re.compile(r"\$\{captured\.(\w+)\.output\}")
        referenced: set[str] = set()
        for d in states.values():
            for m in capture_ref.finditer(d.get("action", "")):
                referenced.add(m.group(1))
        assert referenced & producer_captures, (
            f"Consumer references {referenced} must overlap producer captures {producer_captures}"
        )

    # ------------------------------------------------------------------
    # Step 3 ENH — Signal 5: Numeric Trajectory Stall
    # ------------------------------------------------------------------

    def test_signal5_fixture_has_convergence_evaluator(self) -> None:
        """Signal 5 fixture must include a state with evaluate.type: convergence
        (or output_numeric) — those are the only evaluators that emit numeric values."""
        spec = self._load_fixture("analysis-numeric-stall.yaml")
        states = spec.get("states", {})
        numeric_states = [
            n
            for n, d in states.items()
            if d.get("evaluate", {}).get("type") in ("convergence", "output_numeric")
        ]
        assert numeric_states, (
            "Signal 5 fixture must include a state with evaluate.type in "
            "{convergence, output_numeric}"
        )

    def test_signal5_convergence_state_has_previous_field(self) -> None:
        """Convergence evaluator requires a previous: field so the executor emits
        delta/current and the analyzer can build the numeric trajectory."""
        spec = self._load_fixture("analysis-numeric-stall.yaml")
        states = spec.get("states", {})
        for name, defn in states.items():
            evaluate = defn.get("evaluate", {})
            if evaluate.get("type") == "convergence":
                assert "previous" in evaluate, (
                    f"Convergence state '{name}' must declare evaluate.previous"
                )
                return
        raise AssertionError("No convergence state found in fixture")

    def test_signal5_convergence_state_has_target(self) -> None:
        """Stall detection compares the trajectory mean against evaluate.target —
        the fixture must declare a target so the trigger is well-defined."""
        spec = self._load_fixture("analysis-numeric-stall.yaml")
        states = spec.get("states", {})
        for defn in states.values():
            evaluate = defn.get("evaluate", {})
            if evaluate.get("type") == "convergence":
                assert "target" in evaluate, "Convergence evaluator must declare a target threshold"
                return
        raise AssertionError("No convergence state found in fixture")

    def test_signal5_inline_stddev_below_one_percent_of_mean_flags(self) -> None:
        """Three samples [0.50, 0.501, 0.499] → stddev ~0.001, mean 0.50 →
        0.2% of mean < 1% threshold → flag if target (0.85) not crossed."""
        import statistics

        samples = [0.50, 0.501, 0.499]
        mean = statistics.mean(samples)
        stddev = statistics.stdev(samples)
        target = 0.85
        # Below 1% of mean -> stalled
        assert stddev / mean < 0.01
        # And no sample crossed the target -> signal fires
        assert max(samples) < target

    def test_signal5_inline_high_variance_no_flag(self) -> None:
        """Three samples [0.10, 0.50, 0.90] → stddev ~0.4, mean 0.50 →
        80% of mean >> 1% threshold → not stalled, no signal."""
        import statistics

        samples = [0.10, 0.50, 0.90]
        mean = statistics.mean(samples)
        stddev = statistics.stdev(samples)
        assert stddev / mean > 0.01

    def test_signal5_inline_target_crossed_no_flag(self) -> None:
        """Even with low variance, if any sample crosses the target the trajectory
        is not 'stalled below threshold' and the signal does not fire."""
        samples = [0.86, 0.861, 0.859]
        target = 0.85
        # Low-variance trajectory but already past target → no signal
        assert max(samples) >= target

    # ------------------------------------------------------------------
    # ENH-1373: headless flags
    # ------------------------------------------------------------------

    def test_skill_has_skip_issue_creation_flag(self) -> None:
        skill_path = Path(__file__).parent.parent.parent / "skills" / "debug-loop-run" / "SKILL.md"
        assert "--skip-issue-creation" in skill_path.read_text()

    def test_skill_has_auto_flag(self) -> None:
        skill_path = Path(__file__).parent.parent.parent / "skills" / "debug-loop-run" / "SKILL.md"
        assert "--auto" in skill_path.read_text()

    def test_step5_ask_user_question_guarded_by_skip_flag(self) -> None:
        skill_path = Path(__file__).parent.parent.parent / "skills" / "debug-loop-run" / "SKILL.md"
        content = skill_path.read_text()
        step5_start = content.index("## Step 5:")
        step6_start = content.index("## Step 6:")
        step5_section = content[step5_start:step6_start]
        # The prose guard must appear before AskUserQuestion in Step 5
        guard_pos = step5_section.find("--skip-issue-creation")
        ask_pos = step5_section.find("AskUserQuestion")
        assert guard_pos != -1, "Step 5 must contain --skip-issue-creation guard"
        assert ask_pos != -1, (
            "Step 5 must still contain the AskUserQuestion call for interactive mode"
        )
        assert guard_pos < ask_pos, "Guard must appear before AskUserQuestion in Step 5"

    # ------------------------------------------------------------------
    # Step 5 output grouping (Fault/Effectiveness)
    # ------------------------------------------------------------------

    def test_step5_fault_effectiveness_grouping_assigns_signal3_to_effectiveness(
        self,
    ) -> None:
        """Static-pass Signal 3 (stub action) is an ENH-class effectiveness signal,
        therefore it appears under 'Effectiveness Signals' in Step 5 output, not 'Fault'."""
        # Signal-class taxonomy verification (in-context, no execution)
        fault_signals = {
            "action_failure",
            "sigkill",
            "fatal_error",
            "evaluate_failure",
            "subloop_verdict_discarded",
            "rate_limit_exhaustion",
        }
        effectiveness_signals = {
            "stub_action",  # Signal 3
            "iter1_no_apply",  # Signal 1
            "degenerate_gate",  # Signal 2
            "capture_vacuum",  # Signal 4
            "numeric_stall",  # Signal 5
            "retry_flood",
            "slow_state",
        }
        # No overlap between buckets
        assert not (fault_signals & effectiveness_signals)
        # All five enumerated signals are effectiveness-class
        assert "stub_action" in effectiveness_signals
        assert "iter1_no_apply" in effectiveness_signals
        assert "degenerate_gate" in effectiveness_signals
        assert "capture_vacuum" in effectiveness_signals
        assert "numeric_stall" in effectiveness_signals
