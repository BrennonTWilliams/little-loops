"""Tests for issue_history.workspace_quality — FEAT-3418's workspace-wide totals.

FEAT-3418 extends FEAT-3410's `aggregate_history_dbs()` with an
`AggregationResult.totals: QualityAnalysis` field computed over the union of
all workspace members' `history.db` tables (via multi-ATTACH), and must
resolve the cross-repo `issue_num`/`issue_id` collision problem described in
the issue's Summary: every little-loops repo numbers issues from 1, so a
naive union conflates different repos' issues that happen to share an ID.

Written ahead of FEAT-3418's implementation (TDD "red" state, per
`commands.tdd_mode`) — `AggregationResult` has no `totals` field yet, so both
tests below fail with `AttributeError` until the field and its
ID-discriminator design (Program Design § Decision Rules, Option A) land.
"""

from __future__ import annotations

from pathlib import Path

from little_loops.issue_history.workspace_quality import aggregate_history_dbs
from little_loops.session_store.writers import record_issue_event
from little_loops.workspace import WorkspaceMember


def _member_with_closed_issue(
    tmp_path: Path, name: str, role: str, issue_id: str
) -> WorkspaceMember:
    """A member repo whose history.db records exactly one closed issue.

    Deliberately takes the caller's *bare* ``issue_id`` (unlike FEAT-3410's
    ``_healthy_member``, which prefixes it with the repo name to avoid
    collisions) so two members can be built with the SAME id — reproducing
    the cross-repo collision the issue's Summary describes.
    """
    repo_path = tmp_path / name
    (repo_path / ".issues").mkdir(parents=True)
    (repo_path / ".ll").mkdir()
    db_path = repo_path / ".ll" / f"{name}-history.db"
    record_issue_event(db_path, issue_id, "done")
    return WorkspaceMember(repo_path=repo_path, role=role, db_path=db_path)


class TestWorkspaceTotals:
    """AC: `AggregationResult.totals` populated when run on 2+ non-skipped members."""

    def test_totals_populated_for_two_members(self, tmp_path: Path) -> None:
        m1 = _member_with_closed_issue(tmp_path, "repo_a", "primary", "BUG-1")
        m2 = _member_with_closed_issue(tmp_path, "repo_b", "sibling", "BUG-2")

        result = aggregate_history_dbs(
            [m1, m2], min_sample=1, sensitivity=0.3, baseline_windows=3, latest_only=True
        )

        assert result.totals is not None

    def test_totals_not_conflated_across_id_collision(self, tmp_path: Path) -> None:
        """AC: cross-repo issues sharing the same issue_num/issue_id are not conflated."""
        m1 = _member_with_closed_issue(tmp_path, "repo_a", "primary", "BUG-1")
        m2 = _member_with_closed_issue(tmp_path, "repo_b", "sibling", "BUG-1")

        result = aggregate_history_dbs(
            [m1, m2], min_sample=1, sensitivity=0.3, baseline_windows=3, latest_only=True
        )

        total_closed = sum(w.closed_count for w in result.totals.windows)
        assert total_closed == 2, (
            "both repos' 'BUG-1' closed issue must be counted -- a bare "
            "issue_num/issue_id union would conflate them into 1"
        )
