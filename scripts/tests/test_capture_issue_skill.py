"""Structural tests for the capture-issue skill (ENH-1888)."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
SKILL_FILE = PROJECT_ROOT / "skills" / "capture-issue" / "SKILL.md"


def _phase_text(heading: str) -> str:
    """Return the slice of SKILL.md from `heading` up to the next `### ` heading.

    h3-only match: sibling `#### ` subheadings inside the phase do not terminate
    the slice (test_capture_issue_skill.py convention; see ENH-3283).
    """
    content = SKILL_FILE.read_text()
    start = content.index(heading)
    next_heading = content.find("\n### ", start + 1)
    end = next_heading if next_heading != -1 else len(content)
    return content[start:end]


class TestCaptureIssueNearDuplicateCheck:
    """Phase 2 must document FTS5 near-duplicate check against history.db (ENH-1888)."""

    def _phase_text(self) -> str:
        return _phase_text("### Phase 2: Duplicate Detection")

    def test_ll_session_command_present(self) -> None:
        assert "ll-session" in self._phase_text(), (
            "Phase 2 must include the ll-session search command invocation"
        )

    def test_kind_issue_filter_documented(self) -> None:
        assert "--kind issue" in self._phase_text(), (
            "Phase 2 must document the --kind issue filter for ll-session search"
        )

    def test_graceful_degradation_present(self) -> None:
        text = self._phase_text()
        assert "2>/dev/null" in text or "proceed silently" in text, (
            "Phase 2 must document graceful degradation when history.db is absent"
        )

    def test_find_similar_command_documented(self) -> None:
        text = self._phase_text()
        assert "ll-issues find-similar" in text, (
            "Phase 2 word-overlap scoring must delegate to ll-issues find-similar (ENH-2941)"
        )


class TestCaptureIssueEvidenceQuoteCheck:
    """Phase 4 must document a pre-write evidence-quote verification step (ENH-3283).

    Bounds assertions to the Phase 4 heading slice so they can't accidentally
    match text elsewhere in the file.
    """

    def _phase_text(self) -> str:
        return _phase_text("### Phase 4: Execute Action")

    def test_evidence_check_phrase_present(self) -> None:
        text = self._phase_text()
        assert "quoted span" in text and "cited artifact" in text, (
            "Phase 4 must document a pre-write check of quoted spans against the cited artifact"
        )

    def test_grep_tool_prescribed_not_shell_grep(self) -> None:
        text = self._phase_text()
        assert "Grep` tool" in text, "Phase 4 evidence check must use the Grep tool"
        assert "grep -F" not in text, (
            "Phase 4 must not prescribe shell `grep -F` — this skill has no Bash(grep:*) grant"
        )

    def test_drop_or_correct_instruction_present(self) -> None:
        text = self._phase_text()
        assert "never write the unverified span" in text, (
            "Phase 4 must state the drop-or-correct rule: never write an unverified span"
        )

    def test_at_least_one_non_trigger_class_named(self) -> None:
        text = self._phase_text()
        non_trigger_classes = [
            "Command output",
            "Reproduction steps",
            "Proposed text",
            "Symbol and path names",
        ]
        assert any(cls in text for cls in non_trigger_classes), (
            "Phase 4 must name at least one non-trigger class (command output, "
            "reproduction-step arguments, proposed text, symbol/path references) "
            "so the check does not delete real evidence"
        )

    def test_frontmatter_grants_tools_evidence_check_prescribes(self) -> None:
        content = SKILL_FILE.read_text()
        frontmatter_end = content.index("\n---", content.index("---") + 3)
        frontmatter = content[:frontmatter_end]
        assert "Grep" in frontmatter, (
            "allowed-tools frontmatter must grant Grep for the evidence check"
        )
        assert "Bash(ll-issues:*" in frontmatter, (
            "allowed-tools frontmatter must grant Bash(ll-issues:*) to resolve "
            "an issue ID to a path via `ll-issues show <ID> --json`"
        )
