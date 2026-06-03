"""Doc-wiring regression tests for FEAT-1756: design tokens Round 7 in /ll:init.

Asserts that:
1. skills/init/interactive.md contains a Round 7 block for design tokens
2. skills/init/interactive.md has TOTAL = 8
3. skills/init/SKILL.md references design-tokens in the materialization step
4. skills/init/SKILL.md says "7–8 rounds"
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

INIT_INTERACTIVE = PROJECT_ROOT / "skills" / "init" / "interactive.md"
INIT_SKILL = PROJECT_ROOT / "skills" / "init" / "SKILL.md"


class TestFeat1756InitWiring:
    """skills/init must include Round 7 for design tokens and updated round counts."""

    def test_round_7_design_tokens_present(self) -> None:
        content = INIT_INTERACTIVE.read_text()
        assert "## Round 7: Design Tokens" in content, (
            "skills/init/interactive.md must contain '## Round 7: Design Tokens' "
            "for the design tokens setup step"
        )

    def test_total_is_eight(self) -> None:
        content = INIT_INTERACTIVE.read_text()
        assert "TOTAL = 10" in content, (
            "skills/init/interactive.md must set TOTAL = 10 after adding mandatory Round 9 (analytics)"
        )

    def test_skill_md_references_design_tokens(self) -> None:
        content = INIT_SKILL.read_text()
        assert "design_tokens" in content or "design-tokens" in content, (
            "skills/init/SKILL.md must reference 'design_tokens' or 'design-tokens' "
            "in the materialization step"
        )

    def test_skill_md_round_count_updated(self) -> None:
        content = INIT_SKILL.read_text()
        assert "9–10 rounds" in content, (
            "skills/init/SKILL.md must say '9–10 rounds' (not '8–9 rounds') "
            "after adding mandatory Round 9 (analytics)"
        )
