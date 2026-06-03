"""Doc-wiring regression tests for FEAT-1743: learning_tests in /ll:init.

Asserts that:
1. skills/init/interactive.md contains a Round for learning_tests
2. skills/init/interactive.md has TOTAL = 9
3. skills/init/SKILL.md references learning_tests in the materialization step
4. skills/init/SKILL.md says "8–9 rounds"
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

INIT_INTERACTIVE = PROJECT_ROOT / "skills" / "init" / "interactive.md"
INIT_SKILL = PROJECT_ROOT / "skills" / "init" / "SKILL.md"


class TestFeat1743InitWiring:
    """skills/init must include a learning_tests round and updated round counts."""

    def test_round_learning_tests_present(self) -> None:
        content = INIT_INTERACTIVE.read_text()
        assert "Learning Tests" in content, (
            "skills/init/interactive.md must contain a learning_tests round "
            "with 'Learning Tests' in the round header"
        )

    def test_total_is_nine(self) -> None:
        content = INIT_INTERACTIVE.read_text()
        assert "TOTAL = 10" in content, (
            "skills/init/interactive.md must set TOTAL = 10 after adding "
            "the mandatory analytics round"
        )

    def test_skill_md_references_learning_tests(self) -> None:
        content = INIT_SKILL.read_text()
        assert "learning_tests" in content or "learning-tests" in content, (
            "skills/init/SKILL.md must reference 'learning_tests' or 'learning-tests' "
            "in the materialization step"
        )

    def test_skill_md_round_count_updated(self) -> None:
        content = INIT_SKILL.read_text()
        assert "9–10 rounds" in content, (
            "skills/init/SKILL.md must say '9–10 rounds' (not '8–9 rounds') "
            "after adding the mandatory analytics round"
        )
