"""Tests for ready-issue branch transparency — ENH-2653.

The `ready-issue` verifier must name the branch it inspected and must downgrade a
suspected base-branch-mismatch symbol absence to a non-blocking WARN/concern
rather than a hard NOT_READY. These are prose-spec (Tier 1) assertions against
`commands/ready-issue.md`, mirroring the existing lint-style tests.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
COMMAND_FILE = PROJECT_ROOT / "commands" / "ready-issue.md"


class TestReadyIssueBranchTransparency:
    """commands/ready-issue.md must report the inspected branch (ENH-2653)."""

    def _content(self) -> str:
        return COMMAND_FILE.read_text()

    def test_branch_detection_command_present(self) -> None:
        assert "git rev-parse --abbrev-ref HEAD" in self._content(), (
            "ready-issue must run `git rev-parse --abbrev-ref HEAD` to name the "
            "inspected branch (ENH-2653)"
        )

    def test_worktree_toplevel_reported(self) -> None:
        assert "git rev-parse --show-toplevel" in self._content(), (
            "ready-issue must report the worktree path via "
            "`git rev-parse --show-toplevel` (ENH-2653)"
        )

    def test_detached_head_guard_mentioned(self) -> None:
        text = self._content().lower()
        assert "detached" in text, (
            "branch-report step must guard against detached HEAD (ENH-2653)"
        )

    def test_inspected_branch_in_output_format(self) -> None:
        assert "## INSPECTED_BRANCH" in self._content(), (
            "Output Format must include an ## INSPECTED_BRANCH section naming the "
            "branch that was checked (ENH-2653)"
        )


class TestReadyIssueSymbolExistenceDowngrade:
    """A suspected base-branch mismatch must be a WARN/concern, not NOT_READY (ENH-2653)."""

    def _content(self) -> str:
        return COMMAND_FILE.read_text()

    def test_symbol_existence_validation_row_present(self) -> None:
        assert "Symbol Existence" in self._content(), (
            "VALIDATION table must include a Symbol Existence row (ENH-2653)"
        )

    def test_base_mismatch_downgraded_to_concern(self) -> None:
        text = self._content().lower()
        assert "base" in text and "mismatch" in text, (
            "ready-issue must describe the base-branch mismatch downgrade (ENH-2653)"
        )

    def test_symbol_existence_three_state(self) -> None:
        """Symbol Existence must use the PASS | WARN | NOT_READY three-state shape."""
        content = self._content()
        # Locate the Symbol Existence gate subsection.
        start = content.index("Symbol Existence")
        window = content[start : start + 2600]
        assert "WARN" in window, (
            "Symbol Existence gate must emit WARN for a suspected base mismatch, "
            "not a hard NOT_READY (ENH-2653)"
        )
