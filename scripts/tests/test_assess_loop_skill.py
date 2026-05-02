"""Tests for /ll:assess-loop skill — existence, fixture validation, and logic discriminators.

Modeled after TestAnalyzeLoopSynthesis (test_analyze_loop_synthesis.py) for fixture loading
and TestReviewLoopQualityChecks (test_review_loop.py) for inline discriminator pattern.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from little_loops.fsm.validation import ValidationSeverity, load_and_validate, validate_fsm

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "fsm"

# Threshold keys scanned from context dict (SKILL.md Step 3)
THRESHOLD_KEYS = {
    "target_pass_rate",
    "pass_threshold",
    "quality_threshold",
    "readiness_threshold",
    "outcome_threshold",
    "reward_target",
    "target_score",
    "min_per_category",
    "adversarial_cap",
}


class TestAssessLoopSkill:
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
    # Skill existence checks
    # ------------------------------------------------------------------

    def test_skill_file_exists(self) -> None:
        skill_path = Path(__file__).parent.parent.parent / "skills" / "assess-loop" / "SKILL.md"
        assert skill_path.exists(), "skills/assess-loop/SKILL.md must exist"

    def test_skill_has_loop_name_argument(self) -> None:
        skill_path = Path(__file__).parent.parent.parent / "skills" / "assess-loop" / "SKILL.md"
        content = skill_path.read_text()
        assert "loop_name" in content or "loop-name" in content
        # → skill must accept a loop name argument

    def test_skill_has_tail_argument(self) -> None:
        skill_path = Path(__file__).parent.parent.parent / "skills" / "assess-loop" / "SKILL.md"
        content = skill_path.read_text()
        assert "--tail" in content
        # → skill must support --tail N for limiting history events

    def test_skill_has_no_rubric_audit_flag(self) -> None:
        skill_path = Path(__file__).parent.parent.parent / "skills" / "assess-loop" / "SKILL.md"
        content = skill_path.read_text()
        assert "--no-rubric-audit" in content
        # → skill must support --no-rubric-audit to skip LLM judge calls

    def test_skill_scorecard_has_four_verdicts(self) -> None:
        skill_path = Path(__file__).parent.parent.parent / "skills" / "assess-loop" / "SKILL.md"
        content = skill_path.read_text()
        for verdict in ("met", "phantom", "partial", "degraded"):
            assert f"`{verdict}`" in content or f'"{verdict}"' in content or verdict in content
        # → scorecard verdict must be one of the four defined values

    # ------------------------------------------------------------------
    # Fixture structural validation
    # ------------------------------------------------------------------

    def test_fixture_phantom_success_validates(self) -> None:
        fsm, _ = load_and_validate(FIXTURES_DIR / "assess-phantom-success.yaml")
        errors = validate_fsm(fsm)
        error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        assert not error_list, f"FSM errors: {[str(e) for e in error_list]}"

    def test_fixture_degenerate_gate_validates(self) -> None:
        fsm, _ = load_and_validate(FIXTURES_DIR / "assess-degenerate-gate.yaml")
        errors = validate_fsm(fsm)
        error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        assert not error_list, f"FSM errors: {[str(e) for e in error_list]}"

    def test_fixture_rubric_drift_validates(self) -> None:
        fsm, _ = load_and_validate(FIXTURES_DIR / "assess-rubric-drift.yaml")
        errors = validate_fsm(fsm)
        error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        assert not error_list, f"FSM errors: {[str(e) for e in error_list]}"

    def test_fixture_subloop_laundering_validates(self) -> None:
        fsm, _ = load_and_validate(FIXTURES_DIR / "assess-subloop-laundering.yaml")
        errors = validate_fsm(fsm)
        error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        assert not error_list, f"FSM errors: {[str(e) for e in error_list]}"

    # ------------------------------------------------------------------
    # Discriminator: phantom success
    # ------------------------------------------------------------------

    def test_phantom_success_has_threshold_in_context(self) -> None:
        """Phantom-success fixture must declare a threshold contract in context."""
        spec = self._load_fixture("assess-phantom-success.yaml")
        context = spec.get("context", {})
        threshold_present = any(k in context for k in THRESHOLD_KEYS)
        assert threshold_present
        # → skill should flag as phantom when artifact unchanged despite terminal reached

    def test_phantom_success_evaluate_references_threshold_via_interpolation(self) -> None:
        """Evaluate prompt references threshold only via LLM interpolation — not artifact-verified."""
        spec = self._load_fixture("assess-phantom-success.yaml")
        states = spec.get("states", {})
        initial = spec.get("initial")
        state = states.get(initial, {})
        eval_prompt = state.get("evaluate", {}).get("prompt", "")
        assert "context." in eval_prompt
        # → skill detects threshold is only LLM self-reported, not artifact-verified

    def test_phantom_success_action_references_artifact_path(self) -> None:
        """Action text references the artifact path via context interpolation."""
        spec = self._load_fixture("assess-phantom-success.yaml")
        states = spec.get("states", {})
        initial = spec.get("initial")
        state = states.get(initial, {})
        action = state.get("action", "")
        assert "context.prompt_file" in action
        # → skill should check artifact mutation for this path

    def test_phantom_success_evaluator_type_is_llm_structured(self) -> None:
        """Phantom-success fixture uses llm_structured evaluator — no objective exit criterion."""
        spec = self._load_fixture("assess-phantom-success.yaml")
        states = spec.get("states", {})
        initial = spec.get("initial")
        state = states.get(initial, {})
        assert state.get("evaluate", {}).get("type") == "llm_structured"
        # → skill should flag: llm_structured with no artifact check = phantom risk

    def test_phantom_success_happy_path_reaches_terminal(self) -> None:
        """Happy-path traversal reaches a terminal state (loop appears to succeed)."""
        spec = self._load_fixture("assess-phantom-success.yaml")
        path = self._happy_path(spec)
        states = spec.get("states", {})
        assert states.get(path[-1], {}).get("terminal") is True
        # → loop appears to complete normally; phantom only detected via artifact inspection

    # ------------------------------------------------------------------
    # Discriminator: degenerate gate
    # ------------------------------------------------------------------

    def test_degenerate_gate_uses_exit_code_evaluator(self) -> None:
        """Degenerate-gate fixture uses exit_code evaluator — gate is objectively testable."""
        spec = self._load_fixture("assess-degenerate-gate.yaml")
        states = spec.get("states", {})
        initial = spec.get("initial")
        state = states.get(initial, {})
        assert state.get("evaluate", {}).get("type") == "exit_code"
        # → skill should flag: if shell never exits 0, gate is permanently stuck

    def test_degenerate_gate_on_no_loops_back_to_self(self) -> None:
        """Failure path loops back to the same gate state — loop cannot exit via on_no."""
        spec = self._load_fixture("assess-degenerate-gate.yaml")
        states = spec.get("states", {})
        initial = spec.get("initial")
        state = states.get(initial, {})
        assert state.get("on_no") == initial
        # → skill should flag as degenerate gate

    def test_degenerate_gate_on_error_also_loops_to_self(self) -> None:
        """Error path also returns to the gate — errors cannot escape."""
        spec = self._load_fixture("assess-degenerate-gate.yaml")
        states = spec.get("states", {})
        initial = spec.get("initial")
        state = states.get(initial, {})
        assert state.get("on_error") == initial
        # → skill should flag: error path compounds degeneracy

    def test_degenerate_gate_has_threshold_in_context(self) -> None:
        """Context declares a threshold that exit_code evaluator cannot directly verify."""
        spec = self._load_fixture("assess-degenerate-gate.yaml")
        context = spec.get("context", {})
        threshold_present = any(k in context for k in THRESHOLD_KEYS)
        assert threshold_present
        # → skill should note threshold in context that exit_code cannot confirm

    # ------------------------------------------------------------------
    # Discriminator: rubric drift
    # ------------------------------------------------------------------

    def test_rubric_drift_description_mentions_quality(self) -> None:
        """Description declares a quality/answer-improvement goal."""
        spec = self._load_fixture("assess-rubric-drift.yaml")
        description = spec.get("description", "").lower()
        assert "quality" in description or "answer" in description
        # → declared goal is about quality or answer improvement

    def test_rubric_drift_evaluate_prompt_is_about_syntax(self) -> None:
        """Evaluate prompt measures syntax — unrelated to declared quality goal."""
        spec = self._load_fixture("assess-rubric-drift.yaml")
        states = spec.get("states", {})
        initial = spec.get("initial")
        state = states.get(initial, {})
        eval_prompt = state.get("evaluate", {}).get("prompt", "").lower()
        assert "syntax" in eval_prompt or "python" in eval_prompt
        # → evaluate.prompt measures syntax, not answer quality — rubric drift

    def test_rubric_drift_evaluator_type_is_llm_structured(self) -> None:
        """Rubric-drift fixture uses llm_structured — drift is detectable via judge comparison."""
        spec = self._load_fixture("assess-rubric-drift.yaml")
        states = spec.get("states", {})
        initial = spec.get("initial")
        state = states.get(initial, {})
        assert state.get("evaluate", {}).get("type") == "llm_structured"
        # → skill should send description vs evaluate.prompt to judge for rubric audit

    def test_rubric_drift_description_words_absent_from_evaluate_prompt(self) -> None:
        """Core description keywords do not appear in the evaluate prompt."""
        spec = self._load_fixture("assess-rubric-drift.yaml")
        description_lower = spec.get("description", "").lower()
        states = spec.get("states", {})
        initial = spec.get("initial")
        state = states.get(initial, {})
        eval_prompt_lower = state.get("evaluate", {}).get("prompt", "").lower()
        # "quality" and "answer" appear in description but not in evaluate.prompt
        assert "quality" not in eval_prompt_lower
        assert "answer" not in eval_prompt_lower
        assert "quality" in description_lower
        # → skill should flag as rubric drift (no semantic overlap)

    # ------------------------------------------------------------------
    # Discriminator: sub-loop verdict laundering
    # ------------------------------------------------------------------

    def test_subloop_laundering_has_sub_loop_state(self) -> None:
        """Laundering fixture must contain at least one state with a loop: key."""
        spec = self._load_fixture("assess-subloop-laundering.yaml")
        states = spec.get("states", {})
        sub_loop_states = [n for n, d in states.items() if "loop" in d]
        assert sub_loop_states
        # → skill should check on_yes == on_no for all sub-loop states

    def test_subloop_laundering_on_yes_equals_on_no(self) -> None:
        """Sub-loop state routes success and failure to the same next state."""
        spec = self._load_fixture("assess-subloop-laundering.yaml")
        states = spec.get("states", {})
        for name, defn in states.items():
            if "loop" in defn:
                assert defn.get("on_yes") == defn.get("on_no"), (
                    f"Sub-loop state '{name}' must have on_yes == on_no for laundering fixture"
                )
                # → skill should flag: success indistinguishable from failure

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
        # → regardless of child outcome, parent routes identically — verdict silently discarded

    def test_subloop_laundering_happy_path_reaches_terminal(self) -> None:
        """Happy-path traversal completes normally despite laundering defect."""
        spec = self._load_fixture("assess-subloop-laundering.yaml")
        path = self._happy_path(spec)
        states = spec.get("states", {})
        assert states.get(path[-1], {}).get("terminal") is True
        # → loop completes but child verdict was lost; skill must detect this structurally
