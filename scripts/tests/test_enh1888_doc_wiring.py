"""Doc-wiring tests for ENH-1888: history.db wired into go-no-go and capture-issue.

Asserts that all modified skill/stub files have the correct allowed-tools frontmatter.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
GO_NO_GO_SKILL = PROJECT_ROOT / "skills" / "go-no-go" / "SKILL.md"
CAPTURE_ISSUE_SKILL = PROJECT_ROOT / "skills" / "capture-issue" / "SKILL.md"
LL_GO_NO_GO_STUB = PROJECT_ROOT / "skills" / "ll-go-no-go" / "SKILL.md"
LL_CAPTURE_ISSUE_STUB = PROJECT_ROOT / "skills" / "ll-capture-issue" / "SKILL.md"


def _frontmatter(path: Path) -> str:
    content = path.read_text()
    end = content.index("---", 3)
    return content[: end + 3]


class TestHistoryContextAllowedTools:
    """All 4 modified/created files must include correct allowed-tools frontmatter (ENH-1888)."""

    def test_go_no_go_skill_has_history_context_tool(self) -> None:
        fm = _frontmatter(GO_NO_GO_SKILL)
        assert "Bash(ll-history-context:*)" in fm, (
            "skills/go-no-go/SKILL.md must include Bash(ll-history-context:*) in allowed-tools"
        )

    def test_capture_issue_skill_has_session_tool(self) -> None:
        fm = _frontmatter(CAPTURE_ISSUE_SKILL)
        assert "Bash(ll-session:*)" in fm, (
            "skills/capture-issue/SKILL.md must include Bash(ll-session:*) in allowed-tools"
        )

    def test_ll_go_no_go_stub_has_history_context_tool(self) -> None:
        fm = _frontmatter(LL_GO_NO_GO_STUB)
        assert "Bash(ll-history-context:*)" in fm, (
            "skills/ll-go-no-go/SKILL.md must include Bash(ll-history-context:*) in allowed-tools"
        )

    def test_ll_capture_issue_stub_has_session_tool(self) -> None:
        fm = _frontmatter(LL_CAPTURE_ISSUE_STUB)
        assert "Bash(ll-session:*)" in fm, (
            "skills/ll-capture-issue/SKILL.md must include Bash(ll-session:*) in allowed-tools"
        )

    def test_ll_go_no_go_stub_exists(self) -> None:
        assert LL_GO_NO_GO_STUB.exists(), "skills/ll-go-no-go/SKILL.md bridge stub must exist"

    def test_ll_capture_issue_stub_exists(self) -> None:
        assert LL_CAPTURE_ISSUE_STUB.exists(), (
            "skills/ll-capture-issue/SKILL.md bridge stub must exist"
        )

    def test_ll_go_no_go_stub_has_ll_issues_tool(self) -> None:
        fm = _frontmatter(LL_GO_NO_GO_STUB)
        assert "Bash(ll-issues:*)" in fm, (
            "skills/ll-go-no-go/SKILL.md must include Bash(ll-issues:*) in allowed-tools (FEAT-1896)"
        )
