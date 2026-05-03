"""Tests for ENH-1341: decomposition tree in recursive-refine done summary.

Verifies that the tree_summary context variable and the === Decomposition Tree ===
output block added by ENH-1341 are documented in LOOPS_GUIDE.md.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

LOOPS_GUIDE = PROJECT_ROOT / "docs" / "guides" / "LOOPS_GUIDE.md"


class TestLoopsGuideWiring:
    """docs/guides/LOOPS_GUIDE.md must document tree_summary and the decomposition tree."""

    def test_tree_summary_context_var_present(self) -> None:
        content = LOOPS_GUIDE.read_text()
        assert "tree_summary" in content, (
            "docs/guides/LOOPS_GUIDE.md must include `tree_summary` in the "
            "recursive-refine context-variables table"
        )

    def test_decomposition_tree_header_present(self) -> None:
        content = LOOPS_GUIDE.read_text()
        assert "=== Decomposition Tree ===" in content, (
            "docs/guides/LOOPS_GUIDE.md summary output example must include "
            "the `=== Decomposition Tree ===` block"
        )

    def test_tree_summary_false_documented(self) -> None:
        content = LOOPS_GUIDE.read_text()
        assert "tree_summary: false" in content, (
            "docs/guides/LOOPS_GUIDE.md must document that setting "
            "`tree_summary: false` suppresses the tree block"
        )
