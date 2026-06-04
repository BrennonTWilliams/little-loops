"""Doc-wiring tests for ENH-1905: history.db effort/velocity reads into planning skills.

Asserts that all modified skill/stub files have the correct allowed-tools frontmatter
and that API.md documents the new functions.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
CREATE_SPRINT_CMD = PROJECT_ROOT / "commands" / "create-sprint.md"
SCOPE_EPIC_SKILL = PROJECT_ROOT / "skills" / "scope-epic" / "SKILL.md"
MANAGE_ISSUE_SKILL = PROJECT_ROOT / "skills" / "manage-issue" / "SKILL.md"
REVIEW_EPIC_SKILL = PROJECT_ROOT / "skills" / "review-epic" / "SKILL.md"
LL_CREATE_SPRINT_STUB = PROJECT_ROOT / "skills" / "ll-create-sprint" / "SKILL.md"
API_MD = PROJECT_ROOT / "docs" / "reference" / "API.md"


def _frontmatter(path: Path) -> str:
    content = path.read_text()
    end = content.index("---", 3)
    return content[: end + 3]


class TestHistoryContextAllowedTools:
    """All modified files must include Bash(ll-history-context:*) in allowed-tools (ENH-1905)."""

    def test_create_sprint_has_history_context_tool(self) -> None:
        fm = _frontmatter(CREATE_SPRINT_CMD)
        assert "Bash(ll-history-context:*)" in fm, (
            "commands/create-sprint.md must include Bash(ll-history-context:*) in allowed-tools"
        )

    def test_scope_epic_skill_has_history_context_tool(self) -> None:
        fm = _frontmatter(SCOPE_EPIC_SKILL)
        assert "Bash(ll-history-context:*)" in fm, (
            "skills/scope-epic/SKILL.md must include Bash(ll-history-context:*) in allowed-tools"
        )

    def test_manage_issue_skill_has_history_context_tool(self) -> None:
        fm = _frontmatter(MANAGE_ISSUE_SKILL)
        assert "Bash(ll-history-context:*)" in fm, (
            "skills/manage-issue/SKILL.md must include Bash(ll-history-context:*) in allowed-tools"
        )

    def test_review_epic_skill_has_history_context_tool(self) -> None:
        fm = _frontmatter(REVIEW_EPIC_SKILL)
        assert "Bash(ll-history-context:*)" in fm, (
            "skills/review-epic/SKILL.md must include Bash(ll-history-context:*) in allowed-tools"
        )

    def test_ll_create_sprint_stub_has_history_context_tool(self) -> None:
        fm = _frontmatter(LL_CREATE_SPRINT_STUB)
        assert "Bash(ll-history-context:*)" in fm, (
            "skills/ll-create-sprint/SKILL.md must include Bash(ll-history-context:*) in allowed-tools"
        )


class TestApiDocumentation:
    """API.md must document the new history_reader functions (ENH-1905)."""

    def test_api_documents_issue_effort(self) -> None:
        content = API_MD.read_text()
        assert "issue_effort" in content, (
            "docs/reference/API.md must document the issue_effort() function"
        )

    def test_api_documents_recent_issue_velocity(self) -> None:
        content = API_MD.read_text()
        assert "recent_issue_velocity" in content, (
            "docs/reference/API.md must document the recent_issue_velocity() function"
        )
