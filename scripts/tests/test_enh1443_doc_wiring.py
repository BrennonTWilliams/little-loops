"""Doc-wiring tests for ENH-1443: Goals discovery — documentation softening.

Asserts that:
- Old hard-prerequisite strings are absent from all 5 target doc files
- Softened language is present in each target file
- skills/init/interactive.md no longer implies ll-goals.md is required to enable scan-product
- CONFIGURATION.md includes the goals_discovery behavioral note
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

COMMANDS_MD = PROJECT_ROOT / "docs" / "reference" / "COMMANDS.md"
GETTING_STARTED_MD = PROJECT_ROOT / "docs" / "guides" / "GETTING_STARTED.md"
ISSUE_MANAGEMENT_MD = PROJECT_ROOT / "docs" / "guides" / "ISSUE_MANAGEMENT_GUIDE.md"
HELP_MD = PROJECT_ROOT / "commands" / "help.md"
CONFIGURATION_MD = PROJECT_ROOT / "docs" / "reference" / "CONFIGURATION.md"
INTERACTIVE_MD = PROJECT_ROOT / "skills" / "init" / "interactive.md"


class TestCommandsMdSoftened:
    """docs/reference/COMMANDS.md must not imply ll-goals.md is a hard prerequisite."""

    def test_hard_prerequisite_absent(self) -> None:
        content = COMMANDS_MD.read_text()
        assert "Goals file exists" not in content, (
            "docs/reference/COMMANDS.md must not contain 'Goals file exists' — "
            "ll-goals.md is optional; goals are discovered automatically when it is absent"
        )

    def test_softened_language_present(self) -> None:
        content = COMMANDS_MD.read_text()
        assert (
            "if present; otherwise goals are discovered automatically from project docs" in content
        ), (
            "docs/reference/COMMANDS.md must contain 'if present; otherwise goals are discovered "
            "automatically from project docs' to reflect the discovery fallback"
        )


class TestGettingStartedMdSoftened:
    """docs/guides/GETTING_STARTED.md must not imply goals file is required."""

    def test_hard_prerequisite_absent(self) -> None:
        content = GETTING_STARTED_MD.read_text()
        assert "Requires a product goals file" not in content, (
            "docs/guides/GETTING_STARTED.md must not contain 'Requires a product goals file' — "
            "the goals file is optional; scan-product auto-discovers goals when it is absent"
        )

    def test_softened_language_present(self) -> None:
        content = GETTING_STARTED_MD.read_text()
        assert "discovers goals automatically" in content, (
            "docs/guides/GETTING_STARTED.md must contain 'discovers goals automatically' to "
            "communicate the discovery fallback to new users"
        )


class TestIssueManagementMdSoftened:
    """docs/guides/ISSUE_MANAGEMENT_GUIDE.md prerequisite must be a recommendation, not a mandate."""

    def test_hard_prerequisite_absent(self) -> None:
        content = ISSUE_MANAGEMENT_MD.read_text()
        assert "Goals file exists" not in content, (
            "docs/guides/ISSUE_MANAGEMENT_GUIDE.md must not contain 'Goals file exists' — "
            "the goals file is optional"
        )

    def test_softened_language_present(self) -> None:
        content = ISSUE_MANAGEMENT_MD.read_text()
        assert "scan-product discovers goals from existing docs" in content, (
            "docs/guides/ISSUE_MANAGEMENT_GUIDE.md must contain 'scan-product discovers goals "
            "from existing docs' to document the discovery fallback"
        )


class TestHelpMdSoftened:
    """commands/help.md /ll:scan-product entry must reflect discovery fallback."""

    def test_hard_prerequisite_absent(self) -> None:
        content = HELP_MD.read_text()
        assert "Goals file exists" not in content, (
            "commands/help.md must not contain 'Goals file exists' as a hard prerequisite"
        )

    def test_softened_language_present(self) -> None:
        content = HELP_MD.read_text()
        assert "using goals file if present, or auto-discovering goals" in content, (
            "commands/help.md must contain 'using goals file if present, or auto-discovering "
            "goals' to surface the discovery fallback in the help listing"
        )


class TestConfigurationMdSoftened:
    """docs/reference/CONFIGURATION.md must describe goals file as optional."""

    def test_product_section_softened(self) -> None:
        content = CONFIGURATION_MD.read_text()
        assert "ll-goals.md` is optional" in content, (
            "docs/reference/CONFIGURATION.md must contain 'll-goals.md` is optional' to "
            "correctly describe the product.goals_discovery feature"
        )

    def test_goals_discovery_behavioral_note_present(self) -> None:
        content = CONFIGURATION_MD.read_text()
        assert "These settings are active when `ll-goals.md` is absent" in content, (
            "docs/reference/CONFIGURATION.md must include the behavioral note: "
            "'These settings are active when `ll-goals.md` is absent' in the "
            "### product.goals_discovery section"
        )

    def test_never_block_analysis_note_present(self) -> None:
        content = CONFIGURATION_MD.read_text()
        assert "never block analysis" in content, (
            "docs/reference/CONFIGURATION.md must state that required_files entries "
            "'never block analysis' to clarify warning-only semantics"
        )


class TestInitInteractiveMdSoftened:
    """skills/init/interactive.md must not imply ll-goals.md enables scan-product."""

    def test_old_enables_implication_absent(self) -> None:
        content = INTERACTIVE_MD.read_text()
        assert "enables /ll:scan-product" not in content, (
            "skills/init/interactive.md must not say 'll-goals.md ... enables /ll:scan-product' — "
            "scan-product works without ll-goals.md via discovery fallback"
        )

    def test_softened_language_present(self) -> None:
        content = INTERACTIVE_MD.read_text()
        assert "scan-product works without it" in content, (
            "skills/init/interactive.md must contain 'scan-product works without it' to "
            "communicate that ll-goals.md is optional for product analysis"
        )
