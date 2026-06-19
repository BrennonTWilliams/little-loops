"""Tests for ENH-494: enforce the 500-line SKILL.md limit with flat companion files.

Two guarantees:
1. Every oversized skill has its overflow extracted to a flat companion file
   that exists on disk alongside SKILL.md.
2. No SKILL.md exceeds the 500-line limit (the progressive-disclosure budget).

Follows the structural-test pattern from test_improve_claude_md_skill.py.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# Root of the project relative to this test file
PROJECT_ROOT = Path(__file__).parent.parent.parent
SKILLS_DIR = PROJECT_ROOT / "skills"

SKILL_LINE_LIMIT = 500

# Companion files extracted (or already present) for the skills trimmed by ENH-494.
EXPECTED_COMPANIONS = [
    SKILLS_DIR / "audit-claude-config" / "wave1-prompts.md",
    SKILLS_DIR / "confidence-check" / "rubric.md",
    SKILLS_DIR / "debug-loop-run" / "reference.md",
    SKILLS_DIR / "review-loop" / "reference.md",
    SKILLS_DIR / "manage-issue" / "templates.md",
    SKILLS_DIR / "wire-issue" / "learning-targets.md",
]


class TestCompanionFilesExist:
    """Each oversized skill's overflow lives in a flat companion file on disk."""

    @pytest.mark.parametrize(
        "companion", EXPECTED_COMPANIONS, ids=lambda p: str(p.relative_to(SKILLS_DIR))
    )
    def test_companion_exists(self, companion: Path) -> None:
        assert companion.exists(), (
            f"Companion file not found: {companion.relative_to(PROJECT_ROOT)}\n"
            "ENH-494 extracts oversized SKILL.md overflow into flat companion files."
        )

    @pytest.mark.parametrize(
        "companion", EXPECTED_COMPANIONS, ids=lambda p: str(p.relative_to(SKILLS_DIR))
    )
    def test_companion_non_empty(self, companion: Path) -> None:
        if not companion.exists():
            pytest.skip("existence covered by test_companion_exists")
        assert companion.read_text().strip(), f"Companion file is empty: {companion}"

    @pytest.mark.parametrize(
        "companion", EXPECTED_COMPANIONS, ids=lambda p: str(p.relative_to(SKILLS_DIR))
    )
    def test_skill_links_to_companion(self, companion: Path) -> None:
        """The owning SKILL.md must reference its companion file by name."""
        skill_md = companion.parent / "SKILL.md"
        assert skill_md.exists(), f"SKILL.md missing for {companion.parent}"
        assert companion.name in skill_md.read_text(), (
            f"{skill_md.relative_to(PROJECT_ROOT)} does not link to {companion.name}; "
            "add a 'See [<companion>](<companion>) for ...' pointer at the extraction point."
        )


class TestSkillLineLimit:
    """No SKILL.md may exceed the 500-line progressive-disclosure budget."""

    def test_all_skills_within_limit(self) -> None:
        offenders = []
        for skill_md in sorted(SKILLS_DIR.glob("*/SKILL.md")):
            line_count = len(skill_md.read_text().splitlines())
            if line_count > SKILL_LINE_LIMIT:
                offenders.append((skill_md.relative_to(PROJECT_ROOT), line_count))
        assert not offenders, (
            "SKILL.md files exceed the 500-line limit (ENH-494):\n"
            + "\n".join(f"  {p} = {n} lines" for p, n in offenders)
            + "\nExtract reference/template overflow into a flat companion file."
        )
