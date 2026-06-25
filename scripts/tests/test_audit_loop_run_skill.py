"""Tests for /ll:audit-loop-run skill — existence, fixture validation, and logic discriminators.

Modeled after TestDebugLoopRunSynthesis (test_debug_loop_run_synthesis.py) for fixture loading
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
        skill_path = Path(__file__).parent.parent.parent / "skills" / "audit-loop-run" / "SKILL.md"
        assert skill_path.exists(), "skills/audit-loop-run/SKILL.md must exist"

    def test_skill_has_loop_name_argument(self) -> None:
        skill_path = Path(__file__).parent.parent.parent / "skills" / "audit-loop-run" / "SKILL.md"
        content = skill_path.read_text()
        assert "loop_name" in content or "loop-name" in content
        # → skill must accept a loop name argument

    def test_skill_has_tail_argument(self) -> None:
        skill_path = Path(__file__).parent.parent.parent / "skills" / "audit-loop-run" / "SKILL.md"
        content = skill_path.read_text()
        assert "--tail" in content
        # → skill must support --tail N for limiting history events

    def test_skill_has_no_rubric_audit_flag(self) -> None:
        skill_path = Path(__file__).parent.parent.parent / "skills" / "audit-loop-run" / "SKILL.md"
        content = skill_path.read_text()
        assert "--no-rubric-audit" in content
        # → skill must support --no-rubric-audit to skip LLM judge calls

    def test_skill_has_skip_issue_creation_flag(self) -> None:
        skill_path = Path(__file__).parent.parent.parent / "skills" / "audit-loop-run" / "SKILL.md"
        assert "--skip-issue-creation" in skill_path.read_text()

    def test_skill_has_auto_flag(self) -> None:
        skill_path = Path(__file__).parent.parent.parent / "skills" / "audit-loop-run" / "SKILL.md"
        assert "--auto" in skill_path.read_text()

    def test_step9_ask_user_question_guarded_by_skip_flag(self) -> None:
        skill_path = Path(__file__).parent.parent.parent / "skills" / "audit-loop-run" / "SKILL.md"
        content = skill_path.read_text()
        step9_start = content.index("## Step 9:")
        final_report_start = content.index("## Final Report")
        step9_section = content[step9_start:final_report_start]
        # The prose guard must appear before AskUserQuestion in Step 9
        guard_pos = step9_section.find("--skip-issue-creation")
        ask_pos = step9_section.find("AskUserQuestion")
        assert guard_pos != -1, "Step 9 must contain --skip-issue-creation guard"
        assert ask_pos != -1, (
            "Step 9 must still contain the AskUserQuestion call for interactive mode"
        )
        assert guard_pos < ask_pos, "Guard must appear before AskUserQuestion in Step 9"

    def test_skill_uses_resolved_flag(self) -> None:
        skill_path = Path(__file__).parent.parent.parent / "skills" / "audit-loop-run" / "SKILL.md"
        content = skill_path.read_text()
        assert "--resolved" in content
        # → skill must use --resolved --json for sub-loop visibility in Step 2

    def test_skill_scorecard_has_four_verdicts(self) -> None:
        skill_path = Path(__file__).parent.parent.parent / "skills" / "audit-loop-run" / "SKILL.md"
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

    # ------------------------------------------------------------------
    # Discriminator: shallow-iteration
    # ------------------------------------------------------------------

    def test_shallow_iteration_fixture_validates(self) -> None:
        fsm, _ = load_and_validate(FIXTURES_DIR / "assess-shallow-iteration.yaml")
        errors = validate_fsm(fsm)
        error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        assert not error_list, f"FSM errors: {[str(e) for e in error_list]}"

    def test_shallow_iteration_has_diff_stall_evaluator(self) -> None:
        """Shallow-iteration fixture uses diff_stall evaluator — corroboration signal present."""
        spec = self._load_fixture("assess-shallow-iteration.yaml")
        states = spec.get("states", {})
        initial = spec.get("initial")
        state = states.get(initial, {})
        assert state.get("evaluate", {}).get("type") == "diff_stall"
        # → skill Step 5.5 can use diff_stall verdict as corroboration for shallow-iteration

    def test_shallow_iteration_has_high_max_iterations(self) -> None:
        """Shallow-iteration fixture declares a high max_iterations budget."""
        spec = self._load_fixture("assess-shallow-iteration.yaml")
        assert spec.get("max_iterations", 0) > 30
        # → loop is designed to allow high tool-call counts — shallow-iteration threshold can trigger

    def test_shallow_iteration_primary_artifact_path_in_context(self) -> None:
        """Primary artifact path is declared in context — aux mutations are those outside this."""
        spec = self._load_fixture("assess-shallow-iteration.yaml")
        context = spec.get("context", {})
        path_keys = {"input_file", "output_file", "prompt_file", "system_file"}
        assert any(k in context for k in path_keys)
        # → skill Step 5.5 uses context path keys to define primary artifact paths

    def test_shallow_iteration_on_no_loops_back_to_self(self) -> None:
        """Failure path loops back to the same state — loop can exhaust budget without aux output."""
        spec = self._load_fixture("assess-shallow-iteration.yaml")
        states = spec.get("states", {})
        initial = spec.get("initial")
        state = states.get(initial, {})
        assert state.get("on_no") == initial
        # → loop structure permits high iteration count without guaranteed auxiliary file creation

    def test_shallow_iteration_skill_has_step_55(self) -> None:
        """Skill file contains Step 5.5 (shallow-iteration check)."""
        skill_path = Path(__file__).parent.parent.parent / "skills" / "audit-loop-run" / "SKILL.md"
        content = skill_path.read_text()
        assert "Step 5.5" in content or "5.5" in content
        assert "shallow-iteration" in content.lower() or "shallow_iteration" in content.lower()
        # → skill must implement the shallow-iteration detection step

    def test_shallow_iteration_skill_scorecard_has_check_field(self) -> None:
        """Scorecard block in skill includes a Shallow-iteration check field."""
        skill_path = Path(__file__).parent.parent.parent / "skills" / "audit-loop-run" / "SKILL.md"
        content = skill_path.read_text()
        step6_start = content.index("## Step 6:")
        step7_start = content.index("## Step 7:")
        step6_section = content[step6_start:step7_start]
        assert "Shallow-iteration check" in step6_section
        # → scorecard must surface the shallow-iteration verdict alongside other fields

    def test_shallow_iteration_skill_final_report_has_summary_line(self) -> None:
        """Final Report block includes a Shallow-iteration check summary line."""
        skill_path = Path(__file__).parent.parent.parent / "skills" / "audit-loop-run" / "SKILL.md"
        content = skill_path.read_text()
        final_report_start = content.index("## Final Report")
        final_report_section = content[final_report_start:]
        assert "Shallow-iteration check" in final_report_section
        # → final report must surface the shallow-iteration verdict

    def test_shallow_iteration_skill_threshold_documented(self) -> None:
        """Skill documents the default tool-call threshold (30)."""
        skill_path = Path(__file__).parent.parent.parent / "skills" / "audit-loop-run" / "SKILL.md"
        content = skill_path.read_text()
        assert "30" in content
        # → threshold must be documented so users know when shallow-iteration fires

    def test_shallow_iteration_guide_documents_pattern(self) -> None:
        """HARNESS_OPTIMIZATION_GUIDE.md documents shallow-iteration under runtime failure modes."""
        guide_path = (
            Path(__file__).parent.parent.parent
            / "docs"
            / "guides"
            / "HARNESS_OPTIMIZATION_GUIDE.md"
        )
        content = guide_path.read_text()
        assert "shallow-iteration" in content.lower()
        assert "feature-stubbing" in content.lower()
        # → both patterns must be documented together per acceptance criteria

    def test_shallow_iteration_guide_documents_alongside_feature_stubbing(self) -> None:
        """shallow-iteration and feature-stubbing appear in the same section of the guide."""
        guide_path = (
            Path(__file__).parent.parent.parent
            / "docs"
            / "guides"
            / "HARNESS_OPTIMIZATION_GUIDE.md"
        )
        content = guide_path.read_text()
        shallow_pos = content.lower().find("shallow-iteration")
        stubbing_pos = content.lower().find("feature-stubbing")
        assert shallow_pos != -1 and stubbing_pos != -1
        # They should be within 2000 chars of each other (same section)
        assert abs(shallow_pos - stubbing_pos) < 2000
        # → both patterns co-located for discoverability

    # ------------------------------------------------------------------
    # ENH-2290: auto-scale --tail to run size
    # ------------------------------------------------------------------

    def test_skill_step2_uses_tail_zero_not_200(self) -> None:
        """Step 2 must use --tail 0 (all events) as default, not --tail 200."""
        skill_path = Path(__file__).parent.parent.parent / "skills" / "audit-loop-run" / "SKILL.md"
        content = skill_path.read_text()
        step2_start = content.index("## Step 2:")
        step3_start = content.index("## Step 3:")
        step2_section = content[step2_start:step3_start]
        assert "--tail 200" not in step2_section, (
            "Step 2 must not hardcode --tail 200 as the default tail value"
        )
        assert "--tail 0" in step2_section or "tail_arg_or_0" in step2_section, (
            "Step 2 must use --tail 0 (or tail_arg_or_0 sentinel) as the auto-scaled default"
        )

    def test_skill_step2_derives_event_count_via_wc(self) -> None:
        """Step 2 must derive total event count via 'wc -l' on events.jsonl."""
        skill_path = Path(__file__).parent.parent.parent / "skills" / "audit-loop-run" / "SKILL.md"
        content = skill_path.read_text()
        step2_start = content.index("## Step 2:")
        step3_start = content.index("## Step 3:")
        step2_section = content[step2_start:step3_start]
        assert "wc -l" in step2_section, "Step 2 must use 'wc -l' to derive the total event count"
        assert "events.jsonl" in step2_section, (
            "Step 2 must reference 'events.jsonl' for the event count derivation"
        )

    def test_skill_has_truncation_notice(self) -> None:
        """Skill must include truncation-notice prose for explicit --tail on a larger run."""
        skill_path = Path(__file__).parent.parent.parent / "skills" / "audit-loop-run" / "SKILL.md"
        content = skill_path.read_text()
        assert "partial window" in content or "Loaded last" in content, (
            "Skill must include truncation-notice prose (e.g. 'partial window' or 'Loaded last')"
        )

    def test_skill_tail_description_no_longer_says_default_200(self) -> None:
        """Frontmatter arguments[tail].description must not say 'default 200'."""
        skill_path = Path(__file__).parent.parent.parent / "skills" / "audit-loop-run" / "SKILL.md"
        content = skill_path.read_text()
        # Extract frontmatter block (between first --- and second ---)
        parts = content.split("---", 2)
        assert len(parts) >= 3, "SKILL.md must have YAML frontmatter"
        frontmatter = parts[1]
        assert "default 200" not in frontmatter, (
            "Frontmatter tail argument description must not say 'default 200' after auto-scaling"
        )
