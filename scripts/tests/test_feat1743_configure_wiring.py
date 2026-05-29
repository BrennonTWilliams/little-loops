"""Doc-wiring regression tests for FEAT-1743: learning-tests /ll:configure area and show-output wiring.

Asserts that:
1. skills/configure/SKILL.md contains learning-tests in the area mapping table
2. skills/configure/SKILL.md contains learning-tests in the arguments list
3. skills/configure/areas.md contains ## Area: learning_tests
4. skills/configure/show-output.md contains ## learning_tests --show
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

CONFIGURE_SKILL = PROJECT_ROOT / "skills" / "configure" / "SKILL.md"
CONFIGURE_AREAS = PROJECT_ROOT / "skills" / "configure" / "areas.md"
CONFIGURE_SHOW = PROJECT_ROOT / "skills" / "configure" / "show-output.md"


class TestConfigureSkillMd:
    """skills/configure/SKILL.md must reference learning-tests in area mapping and arguments."""

    def test_area_mapping_table_has_learning_tests(self) -> None:
        content = CONFIGURE_SKILL.read_text()
        assert "learning-tests" in content, (
            "skills/configure/SKILL.md area mapping table must include 'learning-tests'"
        )

    def test_arguments_list_has_learning_tests(self) -> None:
        content = CONFIGURE_SKILL.read_text()
        assert "learning-tests" in content, (
            "skills/configure/SKILL.md ## Arguments list must include 'learning-tests'"
        )


class TestConfigureAreasMd:
    """skills/configure/areas.md must contain the ## Area: learning_tests section."""

    def test_area_section_present(self) -> None:
        content = CONFIGURE_AREAS.read_text()
        assert "## Area: learning_tests" in content, (
            "skills/configure/areas.md must contain '## Area: learning_tests' section"
        )

    def test_fields_present(self) -> None:
        content = CONFIGURE_AREAS.read_text()
        for field in ("enabled", "stale_after_days", "discoverability"):
            assert f"learning_tests.{field}" in content, (
                f"skills/configure/areas.md learning_tests area must reference config field '{field}'"
            )


class TestConfigureShowOutputMd:
    """skills/configure/show-output.md must contain the ## learning_tests --show section."""

    def test_show_section_present(self) -> None:
        content = CONFIGURE_SHOW.read_text()
        assert "## learning_tests --show" in content, (
            "skills/configure/show-output.md must contain '## learning_tests --show' section"
        )

    def test_show_section_has_fields(self) -> None:
        content = CONFIGURE_SHOW.read_text()
        for field in ("enabled", "stale_after_days", "discoverability"):
            assert f"learning_tests.{field}" in content, (
                f"skills/configure/show-output.md learning_tests --show must reference config field '{field}'"
            )
