"""Structural tests for the issue-size-review skill (ENH-1090)."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
SKILL_FILE = PROJECT_ROOT / "skills" / "issue-size-review" / "SKILL.md"


class TestIssueSizeReviewSkillWriteBack:
    """Verify Phase 3 frontmatter write-back is present and correct (ENH-1090)."""

    def test_skill_file_exists(self) -> None:
        """Skill file must be present."""
        assert SKILL_FILE.exists(), "Skill file not found"

    def test_edit_in_allowed_tools(self) -> None:
        """Edit must appear in the allowed-tools section."""
        content = SKILL_FILE.read_text()
        # Find the allowed-tools section in frontmatter
        frontmatter_end = content.index("---", 3)
        frontmatter = content[:frontmatter_end]
        assert "Edit" in frontmatter, (
            "Edit must be listed in allowed-tools so the skill can write back to issue files"
        )

    def test_write_back_phase_exists(self) -> None:
        """Phase 3: Frontmatter Write-back must exist in the skill."""
        content = SKILL_FILE.read_text()
        assert "### Phase 3: Frontmatter Write-back" in content, (
            "Phase 3: Frontmatter Write-back section must be present in SKILL.md"
        )

    def test_no_ask_user_question_in_phase_3(self) -> None:
        """AskUserQuestion must not appear in Phase 3 write-back path."""
        content = SKILL_FILE.read_text()
        phase_3_start = content.index("### Phase 3: Frontmatter Write-back")
        next_heading_idx = content.find("\n###", phase_3_start + 1)
        phase_3_end = next_heading_idx if next_heading_idx != -1 else len(content)
        phase_3_text = content[phase_3_start:phase_3_end]
        assert "AskUserQuestion" not in phase_3_text, (
            "Phase 3 must not use AskUserQuestion — write-back should be unconditional"
        )

    def test_check_mode_skip_guard_in_phase_3(self) -> None:
        """CHECK_MODE skip guard must be present in Phase 3."""
        content = SKILL_FILE.read_text()
        phase_3_start = content.index("### Phase 3: Frontmatter Write-back")
        phase_3_text = content[phase_3_start : phase_3_start + 3000]
        assert "CHECK_MODE" in phase_3_text, (
            "Phase 3 must include a CHECK_MODE skip guard (no writes in check mode)"
        )

    def test_size_key_in_phase_3(self) -> None:
        """The 'size' frontmatter key must appear in Phase 3."""
        content = SKILL_FILE.read_text()
        phase_3_start = content.index("### Phase 3: Frontmatter Write-back")
        phase_3_text = content[phase_3_start : phase_3_start + 3000]
        assert "size" in phase_3_text, "Phase 3 must write 'size' as the frontmatter key"

    def test_six_phase_workflow_header(self) -> None:
        """Workflow header must reflect 6 phases after insertion."""
        content = SKILL_FILE.read_text()
        assert "6-phase workflow" in content, (
            "Workflow header must read '6-phase workflow' after Phase 3 insertion"
        )


class TestIssueSizeReviewQualitativeGuard:
    """Verify Phase 5 qualitative-skip guard is present and correct (ENH-1290)."""

    def _phase5_text(self) -> str:
        content = SKILL_FILE.read_text()
        phase5_start = content.index("### Phase 5: User Approval")
        next_heading = content.find("\n### Phase 6", phase5_start)
        return content[phase5_start:next_heading]

    def test_guard_reads_score_ambiguity(self) -> None:
        """Phase 5 Auto Mode must reference score_ambiguity."""
        assert "score_ambiguity" in self._phase5_text()

    def test_guard_reads_score_complexity(self) -> None:
        """Phase 5 Auto Mode must reference score_complexity."""
        assert "score_complexity" in self._phase5_text()

    def test_guard_reads_outcome_confidence(self) -> None:
        """Phase 5 Auto Mode must reference outcome_confidence."""
        assert "outcome_confidence" in self._phase5_text()

    def test_guard_threshold_ambiguity(self) -> None:
        """Guard must use the 18-point threshold for score_ambiguity."""
        assert "score_ambiguity ≥ 18" in self._phase5_text()

    def test_guard_threshold_complexity(self) -> None:
        """Guard must use the 18-point threshold for score_complexity."""
        assert "score_complexity ≥ 18" in self._phase5_text()

    def test_guard_skip_message_format(self) -> None:
        """Guard must emit the canonical qualitative-skip message."""
        assert "outcome_confidence low is qualitative" in self._phase5_text()

    def test_guard_suggests_refine_or_wire(self) -> None:
        """Skip message must suggest /ll:refine-issue or /ll:wire-issue."""
        text = self._phase5_text()
        assert "/ll:refine-issue" in text and "/ll:wire-issue" in text

    def test_guard_absent_fields_fallthrough(self) -> None:
        """Guard must document absent-fields fallthrough (no confidence-check run)."""
        assert "absent" in self._phase5_text() or "never run" in self._phase5_text()

    def test_guard_does_not_affect_check_mode(self) -> None:
        """CHECK_MODE section must not reference the qualitative guard."""
        content = SKILL_FILE.read_text()
        phase5_start = content.index("### Phase 5: User Approval")
        check_mode_start = content.index("#### Check Mode Behavior", phase5_start)
        next_heading = content.find("\n####", check_mode_start + 1)
        check_mode_text = content[check_mode_start:next_heading]
        assert "score_ambiguity" not in check_mode_text, (
            "Qualitative guard must not appear inside the Check Mode section"
        )

    def test_guard_does_not_affect_interactive_mode(self) -> None:
        """Interactive Mode section must not reference the qualitative guard."""
        content = SKILL_FILE.read_text()
        phase5_start = content.index("### Phase 5: User Approval")
        interactive_start = content.index("#### Interactive Mode", phase5_start)
        next_phase = content.find("\n### Phase 6", interactive_start)
        interactive_text = content[interactive_start:next_phase]
        assert "score_ambiguity" not in interactive_text, (
            "Qualitative guard must not appear inside the Interactive Mode section"
        )
