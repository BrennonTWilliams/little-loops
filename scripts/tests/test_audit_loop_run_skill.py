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

    def test_skill_scorecard_verdicts(self) -> None:
        skill_path = Path(__file__).parent.parent.parent / "skills" / "audit-loop-run" / "SKILL.md"
        content = skill_path.read_text()
        for verdict in ("met", "phantom", "partial", "degraded", "honest-failure"):
            assert f"`{verdict}`" in content or f'"{verdict}"' in content or verdict in content
        # → scorecard must define all five verdict values including honest-failure

    def test_skill_step6_has_honest_failure_verdict(self) -> None:
        """Step 6 verdict table must contain honest-failure as a distinct row from phantom."""
        skill_path = Path(__file__).parent.parent.parent / "skills" / "audit-loop-run" / "SKILL.md"
        content = skill_path.read_text()
        step6_start = content.index("## Step 6:")
        step7_start = content.index("## Step 7:")
        step6_section = content[step6_start:step7_start]
        assert "honest-failure" in step6_section
        assert "phantom" in step6_section
        # → phantom and honest-failure must be distinct rows in the verdict table

    def test_skill_step6_reads_summary_json(self) -> None:
        """Step 6 must reference summary.json to disambiguate honest-failure from phantom."""
        skill_path = Path(__file__).parent.parent.parent / "skills" / "audit-loop-run" / "SKILL.md"
        content = skill_path.read_text()
        step6_start = content.index("## Step 6:")
        step7_start = content.index("## Step 7:")
        step6_section = content[step6_start:step7_start]
        assert "summary.json" in step6_section
        # → skill must cross-check claimed outcome before emitting phantom or honest-failure

    def test_skill_final_report_includes_honest_failure_verdict(self) -> None:
        """Final Report block must include honest-failure in the verdict enum."""
        skill_path = Path(__file__).parent.parent.parent / "skills" / "audit-loop-run" / "SKILL.md"
        content = skill_path.read_text()
        final_report_start = content.index("## Final Report")
        final_report_section = content[final_report_start:]
        assert "honest-failure" in final_report_section
        # → Final Report verdict enum must include honest-failure

    def test_skill_step6a_reads_enh_2404_keys(self) -> None:
        """Step 6a must recognize the additive ENH-2404 summary.json keys
        (skipped_breakdown, gate_blocked, parked_rate) and note legacy back-compat."""
        skill_path = Path(__file__).parent.parent.parent / "skills" / "audit-loop-run" / "SKILL.md"
        content = skill_path.read_text()
        step6_start = content.index("## Step 6:")
        step7_start = content.index("## Step 7:")
        step6_section = content[step6_start:step7_start]
        for key in ("skipped_breakdown", "gate_blocked", "parked_rate"):
            assert key in step6_section, f"Step 6 must mention {key!r}"
        # → must call out that these keys are additive / absent on legacy summaries
        assert "additive" in step6_section.lower() or "legacy" in step6_section.lower()

    def test_skill_step6b_reads_enh_2533_keys(self) -> None:
        """ENH-2533: Step 6b must recognize the additive per_issue and learning_followups
        summary.json keys so per-issue verdicts can cite specific parked IDs (rather than
        only bucketed counters)."""
        skill_path = Path(__file__).parent.parent.parent / "skills" / "audit-loop-run" / "SKILL.md"
        content = skill_path.read_text()
        step6_start = content.index("## Step 6:")
        step7_start = content.index("## Step 7:")
        step6_section = content[step6_start:step7_start]
        for key in ("per_issue", "learning_followups"):
            assert key in step6_section, (
                f"Step 6 must cite {key!r} so audit can attribute per-issue verdicts"
            )
        assert "additive" in step6_section.lower() or "legacy" in step6_section.lower()

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

    def test_fixture_honest_failure_validates(self) -> None:
        fsm, _ = load_and_validate(FIXTURES_DIR / "assess-honest-failure.yaml")
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

    def test_fixture_subloop_laundering_mitigated_validates(self) -> None:
        """Mitigated fixture passes FSM validation with no ERROR-severity issues."""
        fsm, _ = load_and_validate(FIXTURES_DIR / "assess-subloop-laundering-mitigated.yaml")
        errors = validate_fsm(fsm)
        error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        assert not error_list, f"FSM errors: {[str(e) for e in error_list]}"
        # → safe sidecar pattern is structurally valid

    def test_subloop_laundering_mitigated_has_distinct_on_error(self) -> None:
        """Sidecar state routes on_error to a distinct crash state, not the shared classifier."""
        spec = self._load_fixture("assess-subloop-laundering-mitigated.yaml")
        states = spec.get("states", {})
        sidecar_states = [d for d in states.values() if "loop" in d]
        assert sidecar_states, "No sub-loop state found in mitigated fixture"
        for s in sidecar_states:
            shared_target = s.get("on_yes")
            assert s.get("on_error") is not None, "on_error must be set in sidecar state"
            assert s.get("on_error") != shared_target, (
                "on_error must route to a distinct crash state, not the shared classifier"
            )
        # → infrastructure crash is attributed separately from the success/failure path

    def test_subloop_laundering_mitigated_shared_target_reads_artifact(self) -> None:
        """The shared classifier state's action reads subloop_outcome_ (artifact-channel)."""
        spec = self._load_fixture("assess-subloop-laundering-mitigated.yaml")
        states = spec.get("states", {})
        sidecar_states = [d for d in states.values() if "loop" in d]
        assert sidecar_states, "No sub-loop state found in mitigated fixture"
        for s in sidecar_states:
            shared_target = s.get("on_yes")
            assert shared_target in states, f"Shared target '{shared_target}' must exist in states"
            target_action = states[shared_target].get("action", "")
            assert "subloop_outcome_" in target_action, (
                f"Shared target '{shared_target}' must read subloop_outcome_ artifact"
            )
        # → parent recovers child verdict via artifact channel — laundering is mitigated

    def test_subloop_laundering_mitigated_skill_does_not_flag(self) -> None:
        """Step 8 prose exempts the sidecar pattern — artifact-channel check and distinct on_error both required."""
        skill_path = Path(__file__).parent.parent.parent / "skills" / "audit-loop-run" / "SKILL.md"
        assert skill_path.exists(), f"SKILL.md not found: {skill_path}"
        text = skill_path.read_text()
        step8_start = text.find("## Step 8")
        step9_start = text.find("## Step 9")
        assert step8_start != -1, "Step 8 section not found in SKILL.md"
        step8_text = text[step8_start:step9_start] if step9_start != -1 else text[step8_start:]
        assert "subloop_outcome_" in step8_text, (
            "Step 8 must reference 'subloop_outcome_' as the artifact-channel signal to check"
        )
        assert "on_error" in step8_text, (
            "Step 8 must verify on_error routes to a distinct state (not the shared classifier)"
        )
        # → skill suppresses the ENH-2005 sidecar false positive when both conditions hold

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
    # BUG-2482: gitignored run-dir fallback for shallow-iteration heuristic
    # ------------------------------------------------------------------

    def test_shallow_iteration_gitignored_fixture_validates(self) -> None:
        fsm, _ = load_and_validate(FIXTURES_DIR / "assess-shallow-iteration-gitignored.yaml")
        errors = validate_fsm(fsm)
        error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        assert not error_list, f"FSM errors: {[str(e) for e in error_list]}"

    def test_shallow_iteration_gitignored_fixture_uses_run_dir(self) -> None:
        """Primary artifact path is context.run_dir — the gitignored-path case."""
        spec = self._load_fixture("assess-shallow-iteration-gitignored.yaml")
        context = spec.get("context", {})
        assert "run_dir" in context
        assert ".loops/runs" in context["run_dir"]
        # → mirrors the default gitignored run-directory root (.gitignore:80)

    def test_shallow_iteration_skill_step4_lists_run_dir_context_key(self) -> None:
        """Step 4's path-like context key scan list includes context.run_dir."""
        skill_path = Path(__file__).parent.parent.parent / "skills" / "audit-loop-run" / "SKILL.md"
        content = skill_path.read_text()
        step4_start = content.index("## Step 4:")
        step5_start = content.index("## Step 5:")
        step4_section = content[step4_start:step5_start]
        assert "context.run_dir" in step4_section, (
            "Step 4 must list context.run_dir as a candidate path-like context key"
        )

    def test_shallow_iteration_skill_step55_checks_gitignore(self) -> None:
        """Step 5.5 must check git check-ignore before trusting a git-diff-derived AUX_MUTATION_COUNT of 0."""
        skill_path = Path(__file__).parent.parent.parent / "skills" / "audit-loop-run" / "SKILL.md"
        content = skill_path.read_text()
        step55_start = content.index("## Step 5.5:")
        step56_start = content.index("## Step 5.6:")
        step55_section = content[step55_start:step56_start]
        assert "git check-ignore" in step55_section, (
            "Step 5.5 must check git check-ignore against the primary artifact path"
        )

    def test_shallow_iteration_skill_step55_has_filesystem_fallback(self) -> None:
        """Step 5.5 must fall back to a filesystem mutation scan when the primary path is gitignored."""
        skill_path = Path(__file__).parent.parent.parent / "skills" / "audit-loop-run" / "SKILL.md"
        content = skill_path.read_text()
        step55_start = content.index("## Step 5.5:")
        step56_start = content.index("## Step 5.6:")
        step55_section = content[step55_start:step56_start]
        assert "find" in step55_section and "-newermt" in step55_section, (
            "Step 5.5 must use 'find ... -newermt' as the GNU filesystem fallback"
        )
        assert "-newer" in step55_section and "touch -d" in step55_section, (
            "Step 5.5 must document a BSD find fallback (touch -d marker + find -newer)"
        )

    def test_shallow_iteration_skill_step55_documents_unknown_outcome(self) -> None:
        """Step 5.5 must report 'unknown' (not a false 0) when neither git nor filesystem evidence exists."""
        skill_path = Path(__file__).parent.parent.parent / "skills" / "audit-loop-run" / "SKILL.md"
        content = skill_path.read_text()
        step55_start = content.index("## Step 5.5:")
        step56_start = content.index("## Step 5.6:")
        step55_section = content[step55_start:step56_start]
        assert "unknown" in step55_section.lower(), (
            "Step 5.5 must document the 'unknown' outcome when no mutation evidence is available"
        )

    def test_shallow_iteration_verdict_table_admits_unknown(self) -> None:
        """Step 6b Verdict Table's Shallow-iteration check field must admit 'unknown'."""
        skill_path = Path(__file__).parent.parent.parent / "skills" / "audit-loop-run" / "SKILL.md"
        content = skill_path.read_text()
        step6_start = content.index("## Step 6:")
        step7_start = content.index("## Step 7:")
        step6_section = content[step6_start:step7_start]
        idx = step6_section.index("Shallow-iteration check")
        line = step6_section[idx : idx + 200]
        assert "unknown" in line, (
            "Step 6b's Shallow-iteration check field must admit 'unknown' alongside "
            "warning | corroborated | clear"
        )

    def test_shallow_iteration_final_report_admits_unknown(self) -> None:
        """Final Report's Shallow-iteration check line must admit 'unknown'."""
        skill_path = Path(__file__).parent.parent.parent / "skills" / "audit-loop-run" / "SKILL.md"
        content = skill_path.read_text()
        final_report_start = content.index("## Final Report")
        final_report_section = content[final_report_start:]
        idx = final_report_section.index("Shallow-iteration check")
        line = final_report_section[idx : idx + 200]
        assert "unknown" in line, (
            "Final Report's Shallow-iteration check line must admit 'unknown' alongside "
            "warning | corroborated | clear"
        )

    def test_shallow_iteration_guide_documents_gitignore_fallback(self) -> None:
        """HARNESS_OPTIMIZATION_GUIDE.md shallow-iteration row must note the gitignored-path fallback."""
        guide_path = (
            Path(__file__).parent.parent.parent
            / "docs"
            / "guides"
            / "HARNESS_OPTIMIZATION_GUIDE.md"
        )
        content = guide_path.read_text()
        shallow_pos = content.lower().find("shallow-iteration")
        assert shallow_pos != -1
        row_section = content[shallow_pos : shallow_pos + 2000]
        assert "git check-ignore" in row_section or "gitignore" in row_section.lower(), (
            "shallow-iteration guide row must mention the gitignore-aware fallback (BUG-2482)"
        )

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


class TestPIDCorruptionDiscriminator:
    """Discriminator tests for the PID-corruption fixture and audit-loop-run skill heuristic.

    The pattern: action contains $$(cmd) or $$VAR — bash expands $$ to the PID,
    so captured output begins with digits (e.g., "66563(pwd)/66563DIR").
    The audit must flag this as over-escaped-shell-pid-corruption (MR-9), not
    an interpolation sentinel or unparseable path.
    """

    def _load_fixture(self, name: str) -> dict:
        path = FIXTURES_DIR / name
        assert path.exists(), f"Fixture not found: {path}"
        with open(path) as f:
            return yaml.safe_load(f)

    def test_fixture_pid_corruption_validates(self) -> None:
        """PID-corruption fixture passes FSM validation (shell_pid_ok suppresses MR-9)."""
        fsm, _ = load_and_validate(FIXTURES_DIR / "assess-pid-corruption.yaml")
        errors = validate_fsm(fsm)
        error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        assert not error_list, f"FSM errors: {[str(e) for e in error_list]}"

    def test_pid_corruption_action_contains_overescaped_shell(self) -> None:
        """PID-corruption fixture action contains $$(  — the over-escape pattern (MR-9)."""
        spec = self._load_fixture("assess-pid-corruption.yaml")
        states = spec.get("states", {})
        initial = spec.get("initial")
        state = states.get(initial, {})
        action = state.get("action", "")
        assert "$$(" in action or "$$" in action
        # → action has over-escaped shell; $$ expands to PID in bash

    def test_pid_corruption_fixture_captures_output(self) -> None:
        """PID-corruption fixture captures the shell output — the corrupted value lives here."""
        spec = self._load_fixture("assess-pid-corruption.yaml")
        states = spec.get("states", {})
        initial = spec.get("initial")
        state = states.get(initial, {})
        assert state.get("capture") is not None
        # → captured output will contain <pid>(pwd)/<pid>DIR — the PID-corruption artifact

    def test_pid_corruption_skill_step4_has_verbatim_quote_contract(self) -> None:
        """Step 4 must instruct the model to quote captured .output values verbatim."""
        skill_path = Path(__file__).parent.parent.parent / "skills" / "audit-loop-run" / "SKILL.md"
        content = skill_path.read_text()
        step4_start = content.index("## Step 4:")
        step5_start = content.index("## Step 5:")
        step4_section = content[step4_start:step5_start]
        assert "verbatim" in step4_section, (
            "Step 4 must include a verbatim-quote contract for captured .output values"
        )
        assert (
            "sentinel" in step4_section
            or "numeric" in step4_section
            or "interpolation" in step4_section
        ), "Step 4 must note that the interpolation engine emits no numeric markers"

    def test_pid_corruption_skill_step4_corrects_schema_comment(self) -> None:
        """Step 4 captured dict schema must identify keys as capture variable names, not state names."""
        skill_path = Path(__file__).parent.parent.parent / "skills" / "audit-loop-run" / "SKILL.md"
        content = skill_path.read_text()
        step4_start = content.index("## Step 4:")
        step5_start = content.index("## Step 5:")
        step4_section = content[step4_start:step5_start]
        assert "variable" in step4_section or "capture_variable" in step4_section, (
            "Step 4 must clarify that captured dict keys are variable names, not state names"
        )

    def test_pid_corruption_skill_step5_has_pid_heuristic(self) -> None:
        """Step 5 fault-signal list must include the over-escaped-shell-pid-corruption heuristic."""
        skill_path = Path(__file__).parent.parent.parent / "skills" / "audit-loop-run" / "SKILL.md"
        content = skill_path.read_text()
        step5_start = content.index("## Step 5:")
        step55_start = content.index("## Step 5.5:")
        step5_section = content[step5_start:step55_start]
        assert "over-escaped-shell-pid-corruption" in step5_section, (
            "Step 5 must include over-escaped-shell-pid-corruption in the fault-signal list"
        )
        assert "MR-9" in step5_section, (
            "Step 5 must reference MR-9 for the PID-corruption heuristic"
        )

    def test_pid_corruption_skill_step5_recommends_removing_dollar(self) -> None:
        """Step 5 heuristic must recommend removing the extra $, not adding more escaping."""
        skill_path = Path(__file__).parent.parent.parent / "skills" / "audit-loop-run" / "SKILL.md"
        content = skill_path.read_text()
        step5_start = content.index("## Step 5:")
        step55_start = content.index("## Step 5.5:")
        step5_section = content[step5_start:step55_start]
        assert (
            "removing" in step5_section or "remove" in step5_section or "single" in step5_section
        ), "Step 5 PID-corruption heuristic must recommend removing the extra $"

    def test_pid_corruption_skill_has_budget_guard(self) -> None:
        """Skill must include a budget-utilization guard before accepting budget-exhaustion as root cause."""
        skill_path = Path(__file__).parent.parent.parent / "skills" / "audit-loop-run" / "SKILL.md"
        content = skill_path.read_text()
        step5_start = content.index("## Step 5:")
        step6_start = content.index("## Step 6:")
        pre_step6 = content[step5_start:step6_start]
        assert "0.3" in pre_step6, (
            "Skill must include a budget-utilization guard with ratio threshold 0.3 before Step 6"
        )
        assert "loop_complete.iterations" in pre_step6 or "STEPS_CONSUMED" in pre_step6, (
            "Budget guard must derive STEPS_CONSUMED from loop_complete.iterations in events.jsonl"
        )


class TestHonestFailureDiscriminator:
    """Discriminator tests for the honest-failure fixture and its distinguishing properties.

    Parallel to the phantom-success discriminator tests in TestAssessLoopSkill.
    The key distinction: honest-failure means the loop's own summary claims failure
    (implemented == 0, failed > 0) with no artifact mutation — the loop told the truth.
    """

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

    def test_honest_failure_context_has_implemented_counter(self) -> None:
        """Honest-failure fixture declares implemented in context — the claimed-success signal."""
        spec = self._load_fixture("assess-honest-failure.yaml")
        context = spec.get("context", {})
        assert "implemented" in context
        # → skill reads this counter (or equivalent from summary.json) to distinguish from phantom

    def test_honest_failure_claimed_success_is_zero(self) -> None:
        """Honest-failure fixture reports implemented == 0 — no claimed success."""
        spec = self._load_fixture("assess-honest-failure.yaml")
        context = spec.get("context", {})
        assert context.get("implemented", -1) == 0
        # → claimed success == 0; with no mutation → honest-failure, not phantom

    def test_honest_failure_failed_count_is_nonzero(self) -> None:
        """Honest-failure fixture reports failed > 0 — loop explicitly recorded failures."""
        spec = self._load_fixture("assess-honest-failure.yaml")
        context = spec.get("context", {})
        assert context.get("failed", 0) > 0
        # → non-zero failure count confirms this is not silent non-progress

    def test_honest_failure_no_artifact_path_in_context(self) -> None:
        """No output_file or prompt_file in context — no expected artifact mutation to verify."""
        spec = self._load_fixture("assess-honest-failure.yaml")
        context = spec.get("context", {})
        path_keys = {"output_file", "prompt_file", "system_file", "input_file"}
        assert not any(k in context for k in path_keys)
        # → zero claimed-success + no artifact path + no mutation → honest-failure

    def test_honest_failure_happy_path_reaches_terminal(self) -> None:
        """Happy-path traversal reaches terminal — loop completed, failure is self-reported."""
        spec = self._load_fixture("assess-honest-failure.yaml")
        path = self._happy_path(spec)
        states = spec.get("states", {})
        assert states.get(path[-1], {}).get("terminal") is True
        # → loop completes normally; failure is self-reported, not due to SIGKILL/timeout
