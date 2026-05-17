"""Structural tests for the confidence-check skill (ENH-1087)."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
SKILL_FILE = PROJECT_ROOT / "skills" / "confidence-check" / "SKILL.md"


class TestConfidenceCheckPhase4CLI:
    """Phase 4 must use ll-issues set-scores (CLI), not a free-form Edit call (BUG-1307)."""

    def _phase_text(self) -> str:
        content = SKILL_FILE.read_text()
        start = content.index("### Phase 4: Update Frontmatter")
        next_heading = content.find("\n###", start + 1)
        end = next_heading if next_heading != -1 else len(content)
        return content[start:end]

    def test_phase_4_uses_set_scores_cli(self) -> None:
        """Phase 4 must instruct the LLM to call ll-issues set-scores via Bash."""
        assert "ll-issues set-scores" in self._phase_text(), (
            "Phase 4 must use the ll-issues set-scores CLI, not a free-form Edit call (BUG-1307)"
        )

    def test_phase_4_does_not_use_edit_for_frontmatter(self) -> None:
        """Phase 4 must not instruct the LLM to use the Edit tool for frontmatter fields."""
        text = self._phase_text()
        assert "Use the Edit tool" not in text, (
            "Phase 4 must not use the Edit tool for frontmatter — CLI is the single source of truth (BUG-1307)"
        )

    def test_phase_4_heading_exists(self) -> None:
        content = SKILL_FILE.read_text()
        assert "### Phase 4: Update Frontmatter" in content, (
            "SKILL.md must contain a '### Phase 4: Update Frontmatter' section"
        )


class TestConfidenceCheckSkillWriteBack:
    """Verify Phase 4.5 write-back behavior is unconditional (ENH-1087)."""

    def test_skill_file_exists(self) -> None:
        """Skill file must be present."""
        assert SKILL_FILE.exists(), "Skill file not found"

    def test_no_ask_user_question_in_phase_4_5(self) -> None:
        """AskUserQuestion must not appear in Phase 4.5 write-back path."""
        content = SKILL_FILE.read_text()
        phase_4_5_start = content.index("### Phase 4.5: Findings Write-Back")
        # Find the next ### heading after Phase 4.5 to bound the section
        next_heading_idx = content.find("\n###", phase_4_5_start + 1)
        phase_4_5_end = next_heading_idx if next_heading_idx != -1 else len(content)
        phase_4_5_text = content[phase_4_5_start:phase_4_5_end]
        assert "AskUserQuestion" not in phase_4_5_text, (
            "Phase 4.5 must not use AskUserQuestion — write-back should be unconditional"
        )

    def test_check_mode_skip_guard_preserved(self) -> None:
        """CHECK_MODE skip guard must remain in Phase 4.5."""
        content = SKILL_FILE.read_text()
        phase_4_5_start = content.index("### Phase 4.5: Findings Write-Back")
        phase_4_5_text = content[phase_4_5_start : phase_4_5_start + 2000]
        assert "CHECK_MODE" in phase_4_5_text, (
            "Phase 4.5 must preserve the CHECK_MODE skip guard (no writes in check mode)"
        )

    def test_has_findings_gate_preserved(self) -> None:
        """HAS_FINDINGS gate must remain in Phase 4.5."""
        content = SKILL_FILE.read_text()
        phase_4_5_start = content.index("### Phase 4.5: Findings Write-Back")
        phase_4_5_text = content[phase_4_5_start : phase_4_5_start + 2000]
        assert "HAS_FINDINGS" in phase_4_5_text, "Phase 4.5 must preserve the HAS_FINDINGS gate"

    def test_confidence_check_notes_section_name_preserved(self) -> None:
        """The '## Confidence Check Notes' section name must remain in Phase 4.5."""
        content = SKILL_FILE.read_text()
        phase_4_5_start = content.index("### Phase 4.5: Findings Write-Back")
        phase_4_5_text = content[phase_4_5_start : phase_4_5_start + 2000]
        assert "## Confidence Check Notes" in phase_4_5_text, (
            "Phase 4.5 must preserve the '## Confidence Check Notes' section name"
        )


class TestDecisionNeededFlagWriteBack:
    """Phase 4.6 must document setting decision_needed: true when signal phrases found (BUG-1278)."""

    def _phase_text(self) -> str:
        content = SKILL_FILE.read_text()
        start = content.index("### Phase 4.6: Decision-Needed Flag")
        next_heading = content.find("\n###", start + 1)
        end = next_heading if next_heading != -1 else len(content)
        return content[start:end]

    def test_phase_4_6_heading_exists(self) -> None:
        content = SKILL_FILE.read_text()
        assert "Phase 4.6: Decision-Needed Flag" in content, (
            "SKILL.md must contain a 'Phase 4.6: Decision-Needed Flag' section"
        )

    def test_decision_needed_true_in_phase_4_6(self) -> None:
        assert "decision_needed: true" in self._phase_text(), (
            "Phase 4.6 must document setting decision_needed: true in frontmatter"
        )

    def test_signal_phrases_documented(self) -> None:
        text = self._phase_text()
        assert (
            "open decision" in text
            or "unresolved decision" in text
            or "either/or" in text
            or "resolve before starting" in text
            or "open question" in text
        ), "Phase 4.6 must document the signal phrases that trigger the flag"

    def test_idempotency_guard_present(self) -> None:
        text = self._phase_text()
        assert "Idempotency" in text or "idempotent" in text.lower(), (
            "Phase 4.6 must document the idempotency guard (skip if already true)"
        )

    def test_check_mode_guard_in_phase_4_6(self) -> None:
        assert "CHECK_MODE" in self._phase_text(), (
            "Phase 4.6 must include the CHECK_MODE skip guard (no writes in check mode)"
        )

    def test_no_ask_user_question_in_phase_4_6(self) -> None:
        assert "AskUserQuestion" not in self._phase_text(), (
            "Phase 4.6 must not use AskUserQuestion — flag write-back is unconditional"
        )


class TestMissingArtifactsFlagWriteBack:
    """Phase 4.7 must document setting missing_artifacts: true when artifact signal phrases found (ENH-1291)."""

    def _phase_text(self) -> str:
        content = SKILL_FILE.read_text()
        start = content.index("### Phase 4.7: Missing-Artifacts Flag")
        next_heading = content.find("\n###", start + 1)
        end = next_heading if next_heading != -1 else len(content)
        return content[start:end]

    def test_phase_4_7_heading_exists(self) -> None:
        content = SKILL_FILE.read_text()
        assert "Phase 4.7: Missing-Artifacts Flag" in content, (
            "SKILL.md must contain a 'Phase 4.7: Missing-Artifacts Flag' section"
        )

    def test_missing_artifacts_true_in_phase_4_7(self) -> None:
        assert "missing_artifacts: true" in self._phase_text(), (
            "Phase 4.7 must document setting missing_artifacts: true in frontmatter"
        )

    def test_signal_phrases_documented(self) -> None:
        text = self._phase_text()
        assert "not yet created" in text or "does not exist" in text, (
            "Phase 4.7 must document the signal phrases that trigger the flag"
        )

    def test_idempotency_guard_present(self) -> None:
        text = self._phase_text()
        assert "Idempotency" in text or "idempotent" in text.lower(), (
            "Phase 4.7 must document the idempotency guard (skip if already true)"
        )

    def test_check_mode_guard_in_phase_4_7(self) -> None:
        assert "CHECK_MODE" in self._phase_text(), (
            "Phase 4.7 must include the CHECK_MODE skip guard (no writes in check mode)"
        )

    def test_no_ask_user_question_in_phase_4_7(self) -> None:
        assert "AskUserQuestion" not in self._phase_text(), (
            "Phase 4.7 must not use AskUserQuestion — flag write-back is unconditional"
        )

    def test_co_deliverable_suppression_documented(self) -> None:
        text = self._phase_text()
        assert "Files to Create" in text or "co-deliverable" in text.lower(), (
            "Phase 4.7 must document the co-deliverable suppression check before setting the flag"
        )


class TestImplementationOrderRiskFlagWriteBack:
    """Phase 4.9 must document setting implementation_order_risk: true when ordering advice found (ENH-1492)."""

    def _phase_text(self) -> str:
        content = SKILL_FILE.read_text()
        start = content.index("### Phase 4.9: Implementation-Order Risk Flag")
        next_heading = content.find("\n###", start + 1)
        end = next_heading if next_heading != -1 else len(content)
        return content[start:end]

    def test_phase_4_9_heading_exists(self) -> None:
        content = SKILL_FILE.read_text()
        assert "Phase 4.9: Implementation-Order Risk Flag" in content, (
            "SKILL.md must contain a 'Phase 4.9: Implementation-Order Risk Flag' section"
        )

    def test_implementation_order_risk_true_in_phase_4_9(self) -> None:
        assert "implementation_order_risk: true" in self._phase_text(), (
            "Phase 4.9 must document setting implementation_order_risk: true in frontmatter"
        )

    def test_signal_phrases_documented(self) -> None:
        text = self._phase_text()
        assert "co-deliverable" in text or "implement tests first" in text, (
            "Phase 4.9 must document the signal phrases that trigger the flag"
        )

    def test_idempotency_guard_present(self) -> None:
        text = self._phase_text()
        assert "Idempotency" in text or "idempotent" in text.lower(), (
            "Phase 4.9 must document the idempotency guard (skip if already true)"
        )

    def test_check_mode_guard_in_phase_4_9(self) -> None:
        assert "CHECK_MODE" in self._phase_text(), (
            "Phase 4.9 must include the CHECK_MODE skip guard (no writes in check mode)"
        )

    def test_no_ask_user_question_in_phase_4_9(self) -> None:
        assert "AskUserQuestion" not in self._phase_text(), (
            "Phase 4.9 must not use AskUserQuestion — flag write-back is unconditional"
        )


class TestPhase45OutcomeThreshold:
    """Phase 4.5 must use configurable outcome_threshold, not hardcoded 60 (BUG-1289)."""

    def _phase_text(self) -> str:
        content = SKILL_FILE.read_text()
        start = content.index("### Phase 4.5: Findings Write-Back")
        next_heading = content.find("\n###", start + 1)
        end = next_heading if next_heading != -1 else len(content)
        return content[start:end]

    def test_outcome_threshold_referenced_in_phase_4_5(self) -> None:
        """Phase 4.5 must reference outcome_threshold, not hardcoded 60."""
        assert "outcome_threshold" in self._phase_text(), (
            "Phase 4.5 must reference outcome_threshold (not hardcoded 60) so the "
            "Outcome Risk Factors trigger respects the project-configurable threshold"
        )

    def test_hardcoded_60_absent_from_outcome_risk_condition(self) -> None:
        """The hardcoded '< 60' threshold must not appear in the Outcome Risk Factors condition."""
        text = self._phase_text()
        assert "outcome confidence < 60" not in text, (
            "Phase 4.5 must not use hardcoded '< 60'; use outcome_threshold instead (BUG-1289)"
        )

    def test_phase_4_6_guard_uses_outcome_threshold(self) -> None:
        """Phase 4.6 guard must reference outcome_threshold, not hardcoded 60."""
        content = SKILL_FILE.read_text()
        start = content.index("### Phase 4.6: Decision-Needed Flag")
        next_heading = content.find("\n###", start + 1)
        end = next_heading if next_heading != -1 else len(content)
        phase_4_6_text = content[start:end]
        assert "outcome_confidence < 60" not in phase_4_6_text, (
            "Phase 4.6 guard must not use hardcoded '< 60'; use outcome_threshold instead (BUG-1289)"
        )


class TestCriterionDDualPattern:
    """Criterion D must distinguish Pattern A (code blast radius) from Pattern B (enumerated mechanical fanout)."""

    def _criterion_d_text(self) -> str:
        content = SKILL_FILE.read_text()
        start = content.index("#### Criterion D:")
        next_heading = content.find("\n####", start + 1)
        end = next_heading if next_heading != -1 else len(content)
        return content[start:end]

    def test_pattern_a_heading_present(self) -> None:
        assert "Pattern A" in self._criterion_d_text()

    def test_pattern_b_heading_present(self) -> None:
        assert "Pattern B" in self._criterion_d_text()

    def test_verifiability_table_row_present(self) -> None:
        assert "verification grep" in self._criterion_d_text()

    def test_original_count_table_retained_for_pattern_a(self) -> None:
        assert "0-2 callers" in self._criterion_d_text()


class TestCriterionABreadthDepthSplit:
    """Criterion A must be split into Breadth (0-12) and Depth (0-13) sub-scores summing to 25."""

    def _criterion_a_text(self) -> str:
        content = SKILL_FILE.read_text()
        start = content.index("#### Criterion A:")
        next_heading = content.find("\n####", start + 1)
        end = next_heading if next_heading != -1 else len(content)
        return content[start:end]

    def test_breadth_sub_table_present(self) -> None:
        assert "Breadth" in self._criterion_a_text(), "Criterion A must contain a Breadth sub-table"

    def test_depth_sub_table_present(self) -> None:
        assert "Depth" in self._criterion_a_text(), "Criterion A must contain a Depth sub-table"

    def test_breadth_max_is_12(self) -> None:
        assert "0-12" in self._criterion_a_text(), (
            "Criterion A Breadth sub-score must be 0-12 points"
        )

    def test_depth_max_is_13(self) -> None:
        assert "0-13" in self._criterion_a_text(), "Criterion A Depth sub-score must be 0-13 points"

    def test_breadth_detection_method_present(self) -> None:
        text = self._criterion_a_text()
        assert "Integration Map" in text or "Files to Modify" in text, (
            "Criterion A must document Breadth detection method (file enumeration)"
        )

    def test_depth_detection_method_present(self) -> None:
        text = self._criterion_a_text()
        assert "substitute" in text or "rewiring" in text, (
            "Criterion A must document Depth detection method (change-description language)"
        )

    def test_criterion_a_heading_preserved(self) -> None:
        content = SKILL_FILE.read_text()
        assert "#### Criterion A:" in content, (
            "The '#### Criterion A:' heading must be preserved exactly (used as section anchor)"
        )


class TestPhase48LargeFileSurfaceSuppression:
    """Phase 4.8 must exist and mirror the Phase 4.6/4.7 boilerplate."""

    def _phase_text(self) -> str:
        content = SKILL_FILE.read_text()
        start = content.index("### Phase 4.8:")
        next_heading = content.find("\n###", start + 1)
        end = next_heading if next_heading != -1 else len(content)
        return content[start:end]

    def test_phase_4_8_heading_exists(self) -> None:
        assert "Phase 4.8:" in SKILL_FILE.read_text()

    def test_check_mode_guard_present(self) -> None:
        assert "CHECK_MODE" in self._phase_text()

    def test_no_ask_user_question(self) -> None:
        assert "AskUserQuestion" not in self._phase_text()

    def test_signal_phrases_documented(self) -> None:
        text = self._phase_text()
        assert "large file surface" in text or "Signal phrases" in text
