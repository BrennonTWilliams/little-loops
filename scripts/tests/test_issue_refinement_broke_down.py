"""Structural tests for the issue-refinement alias (ENH-2139).

issue-refinement.yaml was converted from a standalone loop to an alias that
delegates to recursive-refine with order=next-action, commit_every=5,
no_recursion=true (ENH-2139).

The check_broke_down gate previously in issue-refinement.yaml has moved to
recursive-refine.yaml, where it was already present with equivalent logic.
"""

from __future__ import annotations

from pathlib import Path

import yaml

BUILTIN_LOOPS_DIR = (
    Path(__file__).parent.parent / "little_loops" / "loops"
)


class TestIssueRefinementAlias:
    """issue-refinement.yaml is an alias for recursive-refine (ENH-2139)."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "issue-refinement.yaml"

    def test_alias_file_exists(self) -> None:
        """issue-refinement.yaml must still exist so eval-driven-development can resolve it."""
        assert self.LOOP_FILE.exists(), (
            "issue-refinement.yaml not found; callers (eval-driven-development.yaml) depend on it"
        )

    def test_alias_delegates_to_recursive_refine(self) -> None:
        """run_all state must call recursive-refine as sub-loop, not inline refinement logic."""
        data = yaml.safe_load(self.LOOP_FILE.read_text())
        state = data.get("states", {}).get("run_all", {})
        assert state.get("loop") == "recursive-refine", (
            f"run_all.loop should be 'recursive-refine', got {state.get('loop')!r}"
        )

    def test_alias_passes_next_action_ordering(self) -> None:
        """Alias must pass order=next-action so ll-issues next-action drives the backlog."""
        data = yaml.safe_load(self.LOOP_FILE.read_text())
        with_ = data.get("states", {}).get("run_all", {}).get("with_", {})
        assert with_.get("order") == "next-action", (
            f"with_.order should be 'next-action', got {with_.get('order')!r}"
        )

    def test_alias_preserves_commit_cadence(self) -> None:
        """Alias must pass commit_every=5 to preserve the periodic commit behavior."""
        data = yaml.safe_load(self.LOOP_FILE.read_text())
        with_ = data.get("states", {}).get("run_all", {}).get("with_", {})
        assert with_.get("commit_every") == 5, (
            f"with_.commit_every should be 5, got {with_.get('commit_every')!r}"
        )

    def test_alias_disables_recursion(self) -> None:
        """Alias must pass no_recursion=true to match old flat one-pass-per-issue behavior."""
        data = yaml.safe_load(self.LOOP_FILE.read_text())
        with_ = data.get("states", {}).get("run_all", {}).get("with_", {})
        assert with_.get("no_recursion") is True, (
            f"with_.no_recursion should be true, got {with_.get('no_recursion')!r}"
        )
