"""Structural tests for the /ll:spike skill and its plan template (FEAT-2567)."""

from __future__ import annotations

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
SKILL_DIR = PROJECT_ROOT / "skills" / "spike"
SKILL_FILE = SKILL_DIR / "SKILL.md"
PLAN_TEMPLATE = SKILL_DIR / "plan-template.md"
OPENAI_YAML = SKILL_DIR / "agents" / "openai.yaml"

# Every mandatory section the spike plan template must carry. The /ll:spike skill
# writes plans in this shape; downstream re-scoring depends on the retired-risk and
# verification sections being present.
MANDATORY_PLAN_SECTIONS = [
    "## Context",
    "## Approach",
    "## Critical files",
    "## Implementation",
    "## Acceptance Criteria",
    "## Verification",
    "## Out of Scope",
    "## Promotion",
]


def _plan_text() -> str:
    return PLAN_TEMPLATE.read_text()


class TestSpikeSkillScaffolding:
    """The skill directory follows the sibling-skill layout convention."""

    def test_skill_file_exists(self) -> None:
        assert SKILL_FILE.exists(), "skills/spike/SKILL.md must exist"

    def test_plan_template_exists(self) -> None:
        assert PLAN_TEMPLATE.exists(), "skills/spike/plan-template.md must exist"

    def test_openai_yaml_stub_exists(self) -> None:
        assert OPENAI_YAML.exists(), (
            "skills/spike/agents/openai.yaml must exist (ll-adapt-skills-for-codex)"
        )

    def test_skill_has_name_frontmatter(self) -> None:
        assert "name: spike" in SKILL_FILE.read_text(), (
            "SKILL.md must declare `name: spike` in frontmatter"
        )

    def test_skill_short_description_within_limit(self) -> None:
        """metadata.short-description must be <=80 chars (Codex integration guard)."""
        for line in SKILL_FILE.read_text().splitlines():
            stripped = line.strip()
            if stripped.startswith("short-description:"):
                value = stripped.split(":", 1)[1].strip()
                assert len(value) <= 80, f"short-description too long ({len(value)}): {value}"
                return
        pytest.fail("SKILL.md is missing a metadata.short-description")


class TestSpikePlanTemplate:
    """The plan template must carry every mandatory section."""

    @pytest.mark.parametrize("section", MANDATORY_PLAN_SECTIONS)
    def test_mandatory_section_present(self, section: str) -> None:
        assert section in _plan_text(), (
            f"plan-template.md is missing the mandatory section: {section}"
        )

    def test_requires_regression_guard_test(self) -> None:
        """A spike must include at least one isolation/regression-guard test."""
        assert "regression-guard" in _plan_text(), (
            "plan-template.md must require a regression-guard (isolation) test"
        )

    def test_spike_code_confined_to_tests_dir(self) -> None:
        """The spike package layout must live under scripts/tests/spike/."""
        assert "scripts/tests/spike/" in _plan_text()

    def test_promotion_path_documented(self) -> None:
        """Promotion moves accepted spike code into the production spike dir."""
        assert "scripts/little_loops/spike/" in _plan_text()


class TestSpikeSkillContract:
    """The skill body must document its phases and flag contract."""

    def test_documents_check_mode_exit_code(self) -> None:
        text = SKILL_FILE.read_text()
        assert "--check" in text and "exit_code" in text, (
            "SKILL.md must document the --check FSM exit-code evaluator contract"
        )

    def test_sets_spike_completed_flag(self) -> None:
        assert "spike_completed: true" in SKILL_FILE.read_text()

    def test_sets_spike_attempted_flag(self) -> None:
        assert "spike_attempted: true" in SKILL_FILE.read_text()

    def test_appends_spike_results_section(self) -> None:
        assert "## Spike Results" in SKILL_FILE.read_text()

    def test_suppresses_external_api_to_explore_api(self) -> None:
        """A risk factor naming an external API routes to /ll:explore-api, not a spike."""
        assert "/ll:explore-api" in SKILL_FILE.read_text()
