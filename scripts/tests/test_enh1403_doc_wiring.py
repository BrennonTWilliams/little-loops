"""Doc-wiring tests for ENH-1403: Remove double-deduplication between product-analyzer and scan-product.

Asserts that:
- Section 6 of skills/product-analyzer/SKILL.md contains the canonical-dedup comment
- Section 2 of skills/product-analyzer/SKILL.md has the conditional GOALS_CONTENT check
- Step 5 of commands/scan-product.md no longer contains "Remove findings marked as duplicates"
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


class TestSkillSection6CanonicalDedup:
    """Section 6 of product-analyzer SKILL.md must declare itself the canonical dedup step."""

    def test_canonical_dedup_comment_present(self) -> None:
        content = SKILL_FILE.read_text()
        section = _section(content, "### 6. Deduplication Check")
        assert "canonical" in section, (
            "Section 6 must contain the word 'canonical' to mark it as the authoritative "
            "deduplication step so callers know not to re-deduplicate"
        )

    def test_callers_must_not_re_deduplicate(self) -> None:
        content = SKILL_FILE.read_text()
        section = _section(content, "### 6. Deduplication Check")
        assert "must not re-deduplicate" in section, (
            "Section 6 must explicitly state that callers must not re-deduplicate"
        )


class TestSkillSection2ConditionalGoalsRead:
    """Section 2 of product-analyzer SKILL.md must check for injected GOALS_CONTENT."""

    def test_goals_content_injection_check_present(self) -> None:
        content = SKILL_FILE.read_text()
        section = _section(content, "### 2. Load Product Goals")
        assert "GOALS_CONTENT" in section, (
            "Section 2 must reference 'GOALS_CONTENT' for the conditional goals-read: "
            "if injected by caller, use it directly; else read from file"
        )

    def test_section2_references_product_goals_file_config(self) -> None:
        content = SKILL_FILE.read_text()
        section = _section(content, "### 2. Load Product Goals")
        assert "product.goals_file" in section, (
            "Section 2 must reference 'product.goals_file' config key "
            "for the standalone (non-injected) read path"
        )


class TestScanProductNoReDedup:
    """commands/scan-product.md Step 5 must not re-deduplicate findings."""

    def test_remove_findings_marked_as_duplicates_absent(self) -> None:
        content = COMMAND_FILE.read_text()
        assert "Remove findings marked as duplicates" not in content, (
            "commands/scan-product.md must not contain 'Remove findings marked as duplicates' — "
            "deduplication is the skill's responsibility; the command trusts the skill's output"
        )

    def test_trust_skill_deduplication_present(self) -> None:
        content = COMMAND_FILE.read_text()
        assert "sole responsible party for deduplication" in content, (
            "commands/scan-product.md must state the skill is the sole responsible party "
            "for deduplication so future editors know not to add re-filtering logic"
        )
