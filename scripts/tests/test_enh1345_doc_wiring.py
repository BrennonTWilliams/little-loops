"""Tests for ENH-1345: recursive-refine max_depth documentation wiring.

Verifies that the max_depth parameter and check_depth gate added by ENH-1344
are documented in LOOPS_GUIDE.md and CONFIGURATION.md.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

LOOPS_GUIDE = PROJECT_ROOT / "docs" / "guides" / "LOOPS_GUIDE.md"
CONFIGURATION = PROJECT_ROOT / "docs" / "reference" / "CONFIGURATION.md"


class TestLoopsGuideWiring:
    """docs/guides/LOOPS_GUIDE.md must document max_depth and check_depth."""

    def test_max_depth_context_var_present(self) -> None:
        content = LOOPS_GUIDE.read_text()
        assert "max_depth" in content, (
            "docs/guides/LOOPS_GUIDE.md must include `max_depth` in the "
            "recursive-refine context-variables table"
        )

    def test_check_depth_fsm_state_present(self) -> None:
        content = LOOPS_GUIDE.read_text()
        assert "check_depth" in content, (
            "docs/guides/LOOPS_GUIDE.md FSM diagram must show `check_depth` state"
        )

    def test_depth_cap_summary_line_present(self) -> None:
        content = LOOPS_GUIDE.read_text()
        assert "Depth-cap" in content, (
            "docs/guides/LOOPS_GUIDE.md summary output example must include "
            "`Depth-cap` row (ENH-1350 renamed from `Skipped (depth-cap N)`)"
        )

    def test_depth_map_tmp_file_present(self) -> None:
        content = LOOPS_GUIDE.read_text()
        assert "recursive-refine-depth-map.txt" in content, (
            "docs/guides/LOOPS_GUIDE.md Notes must document "
            "`recursive-refine-depth-map.txt`"
        )

    def test_current_depth_tmp_file_present(self) -> None:
        content = LOOPS_GUIDE.read_text()
        assert "recursive-refine-current-depth.txt" in content, (
            "docs/guides/LOOPS_GUIDE.md Notes must document "
            "`recursive-refine-current-depth.txt`"
        )

    def test_skipped_depth_tmp_file_present(self) -> None:
        content = LOOPS_GUIDE.read_text()
        assert "recursive-refine-skipped-depth.txt" in content, (
            "docs/guides/LOOPS_GUIDE.md Notes must document "
            "`recursive-refine-skipped-depth.txt`"
        )


class TestConfigurationWiring:
    """docs/reference/CONFIGURATION.md must document commands.recursive_refine.max_depth."""

    def test_recursive_refine_max_depth_present(self) -> None:
        content = CONFIGURATION.read_text()
        assert "recursive_refine.max_depth" in content, (
            "docs/reference/CONFIGURATION.md must document "
            "`commands.recursive_refine.max_depth`"
        )
