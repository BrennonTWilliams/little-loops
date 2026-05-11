"""Doc-wiring tests for ENH-1442: Goals discovery — scan-product, product-analyzer wiring.

Asserts that:
- goals_file_missing is absent from skills/product-analyzer/SKILL.md
- goals_content_missing is present as a valid skipped_reason in SKILL.md
- ### 2. Load Product Goals does not unconditionally return empty findings
- goals_source and discovered_from appear in the analysis_metadata block of SKILL.md
- {{config.product.goals_discovery.max_files}} and {{config.product.goals_discovery.required_files}}
  are present in commands/scan-product.md
- "Goals file not found" hard-exit block is absent from commands/scan-product.md
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

SKILL_FILE = PROJECT_ROOT / "skills" / "product-analyzer" / "SKILL.md"
COMMAND_FILE = PROJECT_ROOT / "commands" / "scan-product.md"


def _section(content: str, heading: str) -> str:
    """Extract content from a section heading to the next same-level heading."""
    start = content.index(heading)
    try:
        end = content.index("\n### ", start + len(heading))
    except ValueError:
        end = len(content)
    return content[start:end]


class TestSkillGuardrails:
    """Guardrails must not block on missing ll-goals.md — discovery mode handles it gracefully."""

    def test_goals_file_missing_absent_from_skill(self) -> None:
        content = SKILL_FILE.read_text()
        assert "goals_file_missing" not in content, (
            "skills/product-analyzer/SKILL.md must not contain 'goals_file_missing' — "
            "discovery mode handles missing ll-goals.md gracefully; this token is a "
            "dead-end stop condition that was replaced by goals_content_missing"
        )


class TestSkillSkippedReason:
    """SKILL.md must expose goals_content_missing as a valid skipped_reason."""

    def test_goals_content_missing_in_skill(self) -> None:
        content = SKILL_FILE.read_text()
        assert "goals_content_missing" in content, (
            "skills/product-analyzer/SKILL.md must include 'goals_content_missing' as a "
            "valid skipped_reason — triggered only when caller omits GOALS_CONTENT entirely "
            "and no discoverable documentation exists"
        )


class TestSkillSection2NoUnconditionalStop:
    """Section 2 must not unconditionally return empty findings when goals file is missing."""

    def test_section2_no_unconditional_return_empty_findings(self) -> None:
        content = SKILL_FILE.read_text()
        section = _section(content, "### 2. Load Product Goals")
        assert "return empty findings" not in section, (
            "Section 2 must not unconditionally return empty findings when goals file is missing — "
            "it should set goals_source: discovered and continue with synthesized content instead"
        )


class TestSkillAnalysisMetadata:
    """analysis_metadata in Output Format must include goals_source and discovered_from."""

    def test_goals_source_in_output_format(self) -> None:
        content = SKILL_FILE.read_text()
        output_section = content[content.index("## Output Format"):]
        assert "goals_source" in output_section, (
            "analysis_metadata in SKILL.md Output Format section must include 'goals_source' "
            "to reflect whether goals came from an explicit ll-goals.md or were auto-discovered"
        )

    def test_discovered_from_in_output_format(self) -> None:
        content = SKILL_FILE.read_text()
        output_section = content[content.index("## Output Format"):]
        assert "discovered_from" in output_section, (
            "analysis_metadata in SKILL.md Output Format section must include 'discovered_from' "
            "to list the files used when goals were auto-discovered (empty/omitted when explicit)"
        )


class TestScanProductGoalsDiscovery:
    """commands/scan-product.md must implement discovery instead of hard-exiting."""

    def test_goals_file_not_found_hard_exit_absent(self) -> None:
        content = COMMAND_FILE.read_text()
        assert "Goals file not found" not in content, (
            "commands/scan-product.md must not contain 'Goals file not found' hard-exit — "
            "when ll-goals.md is missing, discovery mode synthesizes context from other docs"
        )

    def test_goals_discovery_max_files_config_present(self) -> None:
        content = COMMAND_FILE.read_text()
        assert "config.product.goals_discovery.max_files" in content, (
            "commands/scan-product.md must reference 'config.product.goals_discovery.max_files' "
            "to cap the number of files consumed during goals auto-discovery"
        )

    def test_goals_discovery_required_files_config_present(self) -> None:
        content = COMMAND_FILE.read_text()
        assert "config.product.goals_discovery.required_files" in content, (
            "commands/scan-product.md must reference 'config.product.goals_discovery.required_files' "
            "to warn (but not stop) when a required file is absent during discovery"
        )
