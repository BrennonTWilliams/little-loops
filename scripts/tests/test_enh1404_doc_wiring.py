"""Doc-wiring tests for ENH-1404: Add argument-hint and standalone invocation docs to product-analyzer.

Asserts that skills/product-analyzer/SKILL.md has been updated to:
- Include argument-hint: "[focus-area]" in frontmatter
- Include an arguments: block with name: focus-area
- Include a ## Examples section
- Include updated description distinguishing skill from /ll:scan-product
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

SKILL_FILE = PROJECT_ROOT / "skills" / "product-analyzer" / "SKILL.md"


def _frontmatter(content: str) -> str:
    """Extract frontmatter block (between first and second ---)."""
    frontmatter_end = content.index("---", 3)
    return content[:frontmatter_end]


def _section(content: str, heading: str) -> str:
    """Extract content from a section heading to the next same-level heading."""
    start = content.index(heading)
    try:
        end = content.index("\n## ", start + len(heading))
    except ValueError:
        end = len(content)
    return content[start:end]


class TestProductAnalyzerSkillExists:
    def test_file_exists(self) -> None:
        assert SKILL_FILE.exists()


class TestArgumentHintInFrontmatter:
    """Frontmatter must include argument-hint: "[focus-area]" for autocomplete/discoverability."""

    def test_argument_hint_present(self) -> None:
        content = SKILL_FILE.read_text()
        fm = _frontmatter(content)
        assert 'argument-hint: "[focus-area]"' in fm, (
            "skills/product-analyzer/SKILL.md frontmatter must include "
            "'argument-hint: \"[focus-area]\"' for user-invocable argument discoverability"
        )


class TestArgumentsBlockInFrontmatter:
    """Frontmatter must include an arguments: block documenting the focus-area parameter."""

    def test_arguments_block_present(self) -> None:
        content = SKILL_FILE.read_text()
        fm = _frontmatter(content)
        assert "arguments:" in fm, (
            "skills/product-analyzer/SKILL.md frontmatter must include an 'arguments:' block"
        )

    def test_focus_area_argument_documented(self) -> None:
        content = SKILL_FILE.read_text()
        fm = _frontmatter(content)
        assert "name: focus-area" in fm, (
            "skills/product-analyzer/SKILL.md frontmatter arguments: block must include "
            "'name: focus-area' documenting the optional focus-area parameter"
        )


class TestExamplesSectionPresent:
    """SKILL.md must have a ## Examples section after the main content."""

    def test_examples_section_present(self) -> None:
        content = SKILL_FILE.read_text()
        assert "## Examples" in content, (
            "skills/product-analyzer/SKILL.md must include a '## Examples' section "
            "clarifying standalone invocation and raw YAML output"
        )

    def test_examples_reference_scan_product(self) -> None:
        content = SKILL_FILE.read_text()
        section = _section(content, "## Examples")
        assert "scan-product" in section, (
            "## Examples section must reference /ll:scan-product "
            "to direct users to the full workflow with issue file creation"
        )

    def test_examples_section_after_main_content(self) -> None:
        content = SKILL_FILE.read_text()
        main_marker = "REMEMBER: You are a product analyst"
        examples_marker = "## Examples"
        assert content.index(main_marker) < content.index(examples_marker), (
            "## Examples section must appear after the main behavioral content"
        )


class TestDescriptionMentionsScanProduct:
    """Frontmatter description must distinguish the skill from /ll:scan-product."""

    def test_description_mentions_scan_product(self) -> None:
        content = SKILL_FILE.read_text()
        fm = _frontmatter(content)
        assert "scan-product" in fm, (
            "skills/product-analyzer/SKILL.md frontmatter description must mention "
            "'scan-product' to distinguish raw YAML skill output from full workflow command"
        )
