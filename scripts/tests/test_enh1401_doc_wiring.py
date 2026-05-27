"""Doc-wiring tests for ENH-1401: Wire product setup into init — create goals template and config.

Asserts that skills/init/SKILL.md and skills/init/interactive.md have been updated to include
product.enabled in generated config and deploy .ll/ll-goals.md during init.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

INIT_SKILL = PROJECT_ROOT / "skills" / "init" / "SKILL.md"
INIT_INTERACTIVE = PROJECT_ROOT / "skills" / "init" / "interactive.md"
ISSUE_MGMT_GUIDE = PROJECT_ROOT / "docs" / "guides" / "ISSUE_MANAGEMENT_GUIDE.md"
CONFIGURATION = PROJECT_ROOT / "docs" / "reference" / "CONFIGURATION.md"


class TestInitSkillProductSetup:
    """skills/init/SKILL.md must include product.enabled in config and deploy goals template."""

    def test_file_exists(self) -> None:
        assert INIT_SKILL.exists()

    def test_no_product_strip_instruction(self) -> None:
        content = INIT_SKILL.read_text()
        assert "Strip the `_meta`, `$schema`, and `product` sections" not in content, (
            "skills/init/SKILL.md must not strip the product section — "
            "product.enabled: true should be included in generated config"
        )

    def test_product_enabled_in_yes_path(self) -> None:
        content = INIT_SKILL.read_text()
        assert "product.enabled: true" in content, (
            "skills/init/SKILL.md must include 'product.enabled: true' in the --yes config path"
        )

    def test_goals_template_deploy_step(self) -> None:
        content = INIT_SKILL.read_text()
        assert "ll-goals-template.md" in content, (
            "skills/init/SKILL.md must reference templates/ll-goals-template.md "
            "as the source for .ll/ll-goals.md deployment"
        )

    def test_goals_file_existence_guard(self) -> None:
        content = INIT_SKILL.read_text()
        assert ".ll/ll-goals.md" in content, (
            "skills/init/SKILL.md must reference .ll/ll-goals.md in the deploy step"
        )
        assert "already exist" in content, (
            "skills/init/SKILL.md must include an existence guard to avoid overwriting "
            "an existing .ll/ll-goals.md"
        )

    def test_dry_run_shows_goals_file(self) -> None:
        content = INIT_SKILL.read_text()
        assert "[write]  .ll/ll-goals.md" in content, (
            "skills/init/SKILL.md dry-run preview must list '[write]  .ll/ll-goals.md' "
            "so users can see what --dry-run would create"
        )

    def test_completion_message_shows_goals_file(self) -> None:
        content = INIT_SKILL.read_text()
        assert "Created: .ll/ll-goals.md" in content, (
            "skills/init/SKILL.md completion message must show 'Created: .ll/ll-goals.md' "
            "when product is enabled"
        )


class TestInitInteractiveProductRound:
    """skills/init/interactive.md must include Round 4 for product analysis opt-in."""

    def test_file_exists(self) -> None:
        assert INIT_INTERACTIVE.exists()

    def test_total_is_seven(self) -> None:
        content = INIT_INTERACTIVE.read_text()
        assert "TOTAL = 8" in content, (
            "skills/init/interactive.md must set TOTAL = 8 after adding mandatory Round 7 (design tokens)"
        )

    def test_round_4_present(self) -> None:
        content = INIT_INTERACTIVE.read_text()
        assert "Round 4" in content, (
            "skills/init/interactive.md must contain 'Round 4' for the product analysis step"
        )

    def test_round_4_yes_option(self) -> None:
        content = INIT_INTERACTIVE.read_text()
        assert "Yes, enable product analysis" in content, (
            "skills/init/interactive.md Round 4 must offer a 'Yes, enable product analysis' option"
        )

    def test_round_4_no_option(self) -> None:
        content = INIT_INTERACTIVE.read_text()
        assert "No, skip" in content, (
            "skills/init/interactive.md Round 4 must offer a 'No, skip' option"
        )

    def test_product_enabled_tracking(self) -> None:
        content = INIT_INTERACTIVE.read_text()
        assert "PRODUCT_ENABLED=true" in content, (
            "skills/init/interactive.md must track PRODUCT_ENABLED=true when user opts in, "
            "signalling Step 8 to deploy the goals template"
        )


class TestIssueManagementGuideUpdated:
    """docs/guides/ISSUE_MANAGEMENT_GUIDE.md must not instruct manual ll-goals.md copy."""

    def test_file_exists(self) -> None:
        assert ISSUE_MGMT_GUIDE.exists()

    def test_no_manual_copy_instruction(self) -> None:
        content = ISSUE_MGMT_GUIDE.read_text()
        assert "create `ll-goals.md` by copying `templates/ll-goals-template.md`" not in content, (
            "docs/guides/ISSUE_MANAGEMENT_GUIDE.md must not instruct manual copy of "
            "templates/ll-goals-template.md — /ll:init now handles this automatically"
        )


class TestConfigurationDocUpdated:
    """docs/reference/CONFIGURATION.md must reflect product as a first-class init output."""

    def test_file_exists(self) -> None:
        assert CONFIGURATION.exists()

    def test_init_path_mentioned_for_product(self) -> None:
        content = CONFIGURATION.read_text()
        assert "/ll:init" in content and "product.enabled" in content, (
            "docs/reference/CONFIGURATION.md must mention /ll:init as the path for setting "
            "product.enabled for new projects"
        )
