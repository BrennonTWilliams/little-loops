"""Doc-wiring tests for ENH-1847: ll-history-context wired into refinement skills.

Asserts that all five modified skill/command files have Bash(ll-history-context:*)
in their allowed-tools frontmatter.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
REFINE_ISSUE_CMD = PROJECT_ROOT / "commands" / "refine-issue.md"
READY_ISSUE_CMD = PROJECT_ROOT / "commands" / "ready-issue.md"
CONFIDENCE_CHECK_SKILL = PROJECT_ROOT / "skills" / "confidence-check" / "SKILL.md"
LL_REFINE_ISSUE_STUB = PROJECT_ROOT / "skills" / "ll-refine-issue" / "SKILL.md"
LL_READY_ISSUE_STUB = PROJECT_ROOT / "skills" / "ll-ready-issue" / "SKILL.md"


def _frontmatter(path: Path) -> str:
    content = path.read_text()
    end = content.index("---", 3)
    return content[: end + 3]


class TestHistoryContextAllowedTools:
    """All 5 modified files must include Bash(ll-history-context:*) in allowed-tools frontmatter."""

    def test_refine_issue_cmd_has_allowed_tool(self) -> None:
        fm = _frontmatter(REFINE_ISSUE_CMD)
        assert "Bash(ll-history-context:*)" in fm, (
            "commands/refine-issue.md must include Bash(ll-history-context:*) in allowed-tools"
        )

    def test_ready_issue_cmd_has_allowed_tool(self) -> None:
        fm = _frontmatter(READY_ISSUE_CMD)
        assert "Bash(ll-history-context:*)" in fm, (
            "commands/ready-issue.md must include Bash(ll-history-context:*) in allowed-tools"
        )

    def test_confidence_check_skill_has_allowed_tool(self) -> None:
        fm = _frontmatter(CONFIDENCE_CHECK_SKILL)
        assert "Bash(ll-history-context:*)" in fm, (
            "skills/confidence-check/SKILL.md must include Bash(ll-history-context:*) in allowed-tools"
        )

    def test_ll_refine_issue_stub_has_allowed_tool(self) -> None:
        fm = _frontmatter(LL_REFINE_ISSUE_STUB)
        assert "Bash(ll-history-context:*)" in fm, (
            "skills/ll-refine-issue/SKILL.md must include Bash(ll-history-context:*) in allowed-tools"
        )

    def test_ll_ready_issue_stub_has_allowed_tool(self) -> None:
        fm = _frontmatter(LL_READY_ISSUE_STUB)
        assert "Bash(ll-history-context:*)" in fm, (
            "skills/ll-ready-issue/SKILL.md must include Bash(ll-history-context:*) in allowed-tools"
        )
