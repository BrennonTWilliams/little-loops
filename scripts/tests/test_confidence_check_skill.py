"""Structural tests for the confidence-check skill (ENH-1087)."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
SKILL_FILE = PROJECT_ROOT / "skills" / "confidence-check" / "SKILL.md"


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
