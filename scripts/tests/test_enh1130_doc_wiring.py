"""Tests for ENH-1130: scratch-pad documentation and path updates.

Verifies that CLAUDE.md references the correct scratch path (.loops/tmp/scratch/)
and that LOOPS_GUIDE.md uses the correct FSM default (.loops/tmp) in the
scratch_dir CLI override example — and that the old /tmp/ll-scratch path
no longer appears in either file.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

CLAUDE_MD = PROJECT_ROOT / ".claude" / "CLAUDE.md"
LOOPS_GUIDE = PROJECT_ROOT / "docs" / "guides" / "LOOPS_GUIDE.md"


class TestClaudeMdScratchPadWiring:
    """.claude/CLAUDE.md must reference the current scratch path."""

    def test_correct_scratch_path_present(self) -> None:
        content = CLAUDE_MD.read_text()
        assert ".loops/tmp/scratch/" in content, (
            ".claude/CLAUDE.md must reference `.loops/tmp/scratch/` as the active scratch path"
        )

    def test_old_scratch_path_absent(self) -> None:
        content = CLAUDE_MD.read_text()
        assert "/tmp/ll-scratch" not in content, (
            ".claude/CLAUDE.md must not reference the old `/tmp/ll-scratch` path "
            "(migrated to `.loops/tmp/scratch/` by BUG-817)"
        )


class TestLoopsGuideScratchDirWiring:
    """docs/guides/LOOPS_GUIDE.md must use the FSM-default scratch_dir path."""

    def test_correct_scratch_dir_override_present(self) -> None:
        content = LOOPS_GUIDE.read_text()
        assert "scratch_dir=.loops/tmp" in content, (
            "docs/guides/LOOPS_GUIDE.md scratch_dir CLI override example must use "
            "`scratch_dir=.loops/tmp` (the FSM default from context-health-monitor.yaml)"
        )

    def test_old_scratch_dir_override_absent(self) -> None:
        content = LOOPS_GUIDE.read_text()
        assert "scratch_dir=/tmp/ll-scratch" not in content, (
            "docs/guides/LOOPS_GUIDE.md must not reference `scratch_dir=/tmp/ll-scratch` "
            "(old path, replaced by `.loops/tmp`)"
        )
