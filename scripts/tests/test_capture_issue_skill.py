"""Structural tests for the capture-issue skill (ENH-1888)."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
SKILL_FILE = PROJECT_ROOT / "skills" / "capture-issue" / "SKILL.md"


class TestCaptureIssueNearDuplicateCheck:
    """Phase 2 must document FTS5 near-duplicate check against history.db (ENH-1888)."""

    def _phase_text(self) -> str:
        content = SKILL_FILE.read_text()
        start = content.index("### Phase 2: Duplicate Detection")
        next_heading = content.find("\n### ", start + 1)
        end = next_heading if next_heading != -1 else len(content)
        return content[start:end]

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
