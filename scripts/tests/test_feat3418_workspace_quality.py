"""Tests for issue_history.workspace_quality — FEAT-3418's workspace-wide totals.

FEAT-3418 extends FEAT-3410's `aggregate_history_dbs()` with an
`AggregationResult.totals: QualityAnalysis | None` field computed over the
union of all workspace members' `history.db` tables (via multi-ATTACH), and
resolves the cross-repo `issue_num`/`issue_id` collision problem described in
the issue's Summary: every little-loops repo numbers issues from 1, so a
naive union conflates different repos' issues that happen to share an ID.

Mechanism under test (Program Design § Decision Rules, Option C): **TEMP**
union views (never ``main`` — SQLite rejects a ``main``-schema view that
references any attached-schema object) whose ``issue_id``/``issue_num``
columns carry a ``#r{i}`` suffix / ``i * STRIDE`` offset per member, plus a
symmetrically suffixed on-disk `issues` list for the `supersedes:` join.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from little_loops.issue_history import workspace_quality
from little_loops.issue_history.rework import analyze_rework
from little_loops.issue_history.workspace_quality import (
    _UNION_RELATIONS,
    _discriminate_issues,
    _discriminator,
    _open_union,
    aggregate_history_dbs,
)
from little_loops.issue_parser import IssueInfo
from little_loops.session_store.writers import (
    record_commit_event,
    record_issue_event,
    record_usage_event,
)
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


def _bare_member(tmp_path: Path, name: str, role: str) -> WorkspaceMember:
    """A member repo directory with no history.db rows yet -- caller writes its own."""
    repo_path = tmp_path / name
    (repo_path / ".issues").mkdir(parents=True)
    (repo_path / ".ll").mkdir()
    db_path = repo_path / ".ll" / f"{name}-history.db"
    return WorkspaceMember(repo_path=repo_path, role=role, db_path=db_path)


def _stamp_ts(db: Path, issue_id: str, transition: str, ts: str) -> None:
    conn = sqlite3.connect(str(db))
    try:
        conn.execute(
            "UPDATE issue_events SET ts = ? WHERE issue_id = ? AND transition = ?",
            (ts, issue_id, transition),
        )
        conn.commit()
    finally:
        conn.close()


def _close(db: Path, issue_id: str, ts: str) -> None:
    record_issue_event(db, issue_id, "done", completed_at=ts)
    _stamp_ts(db, issue_id, "done", ts)


def _reopen(db: Path, issue_id: str, ts: str, transition: str = "open") -> None:
    record_issue_event(db, issue_id, transition)
    _stamp_ts(db, issue_id, transition, ts)


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


class TestTotalsEdgeCounts:
    def test_one_member_totals_equals_its_per_repo_entry(self, tmp_path: Path) -> None:
        m1 = _member_with_closed_issue(tmp_path, "repo_a", "primary", "BUG-1")

        result = aggregate_history_dbs(
            [m1], min_sample=1, sensitivity=0.3, baseline_windows=3, latest_only=True
        )

        assert result.totals is not None
        assert result.totals.to_dict() == result.per_repo["repo_a (primary)"].to_dict()

    def test_zero_analyzable_members_totals_is_none(self, tmp_path: Path) -> None:
        result = aggregate_history_dbs(
            [], min_sample=1, sensitivity=0.3, baseline_windows=3, latest_only=True
        )

        assert result.totals is None
        assert result.totals_skipped == "no analyzable members"


class TestAttachLimitGuard:
    """AC: an oversized workspace never attaches a truncated subset."""

    def test_exceeding_the_attach_limit_skips_totals_but_keeps_per_repo(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(workspace_quality, "_attach_limit", lambda conn: 1)
        m1 = _member_with_closed_issue(tmp_path, "repo_a", "primary", "BUG-1")
        m2 = _member_with_closed_issue(tmp_path, "repo_b", "sibling", "BUG-2")

        result = aggregate_history_dbs(
            [m1, m2], min_sample=1, sensitivity=0.3, baseline_windows=3, latest_only=True
        )

        assert result.totals is None
        assert result.totals_skipped is not None
        assert "2" in result.totals_skipped
        assert "1" in result.totals_skipped
        assert set(result.per_repo) == {"repo_a (primary)", "repo_b (sibling)"}


class TestUnionViewCoverage:
    """AC: all 9 relations exist as TEMP views and counts sum across members."""

    def test_nine_temp_views_and_summed_counts(self, tmp_path: Path) -> None:
        m1 = _member_with_closed_issue(tmp_path, "repo_a", "primary", "BUG-1")
        m2 = _member_with_closed_issue(tmp_path, "repo_b", "sibling", "BUG-2")
        record_issue_event(m1.db_path, "BUG-1", "in_progress", session_id="sess-a")
        record_issue_event(m2.db_path, "BUG-2", "in_progress", session_id="sess-b")
        record_usage_event(
            m1.db_path,
            run_id="run-a",
            ts="2026-01-01T00:00:00Z",
            state="build",
            model="test-model",
            input_tokens=1,
            output_tokens=1,
            cache_read_tokens=0,
            cache_creation_tokens=0,
        )
        record_usage_event(
            m2.db_path,
            run_id="run-b",
            ts="2026-01-01T00:00:00Z",
            state="build",
            model="test-model",
            input_tokens=1,
            output_tokens=1,
            cache_read_tokens=0,
            cache_creation_tokens=0,
        )

        conn = _open_union([m1.db_path, m2.db_path])
        try:
            names = {
                row["name"]
                for row in conn.execute("SELECT name FROM sqlite_temp_master WHERE type='view'")
            }
            assert names == set(_UNION_RELATIONS)
            assert not conn.execute(
                "SELECT name FROM main.sqlite_master WHERE type='view'"
            ).fetchall(), "the union views must live in TEMP, never main"

            for relation in ("issue_events", "issue_sessions", "usage_events"):
                union_count = conn.execute(f"SELECT COUNT(*) FROM {relation}").fetchone()[0]
                member_total = 0
                for db_path in (m1.db_path, m2.db_path):
                    member_conn = sqlite3.connect(str(db_path))
                    try:
                        member_total += member_conn.execute(
                            f"SELECT COUNT(*) FROM {relation}"
                        ).fetchone()[0]
                    finally:
                        member_conn.close()
                assert union_count == member_total, relation
        finally:
            conn.close()


class TestSupersedesScopedPerMember:
    """AC: a cross-repo `supersedes:` edge must not reopen another member's same-id issue."""

    def test_cross_repo_supersedes_does_not_reopen_but_same_repo_edge_does(
        self, tmp_path: Path
    ) -> None:
        m1 = _bare_member(tmp_path, "repo_a", "primary")
        m2 = _bare_member(tmp_path, "repo_b", "sibling")

        _close(m1.db_path, "BUG-1", "2026-03-01T00:00:00Z")
        _reopen(m1.db_path, "BUG-1", "2026-03-05T00:00:00Z", transition="cancelled")

        _close(m2.db_path, "BUG-1", "2026-03-01T00:00:00Z")
        _reopen(m2.db_path, "BUG-1", "2026-03-05T00:00:00Z", transition="cancelled")

        # repo A: BUG-1 cancelled, no supersedes edge anywhere in repo A.
        issues_a = [
            IssueInfo(
                path=Path("a.md"), issue_type="bugs", priority="P2", issue_id="BUG-1", title="BUG-1"
            )
        ]
        # repo B: BUG-1 cancelled, and repo B's own FEAT-9 supersedes it --
        # a same-repo edge, which must still count as reopened.
        issues_b = [
            IssueInfo(
                path=Path("b1.md"),
                issue_type="bugs",
                priority="P2",
                issue_id="BUG-1",
                title="BUG-1",
            ),
            IssueInfo(
                path=Path("b2.md"),
                issue_type="features",
                priority="P2",
                issue_id="FEAT-9",
                title="FEAT-9",
                supersedes=["BUG-1"],
            ),
        ]

        combined = _discriminate_issues(issues_a, _discriminator(0)) + _discriminate_issues(
            issues_b, _discriminator(1)
        )

        conn = _open_union([m1.db_path, m2.db_path])
        try:
            analysis = analyze_rework(combined, conn=conn, min_sample=1)
        finally:
            conn.close()

        w = next(w for w in analysis.windows if w.period == "2026-03")
        assert w.closed_count == 2
        assert w.reopen.rate == 1 / 2, (
            "only repo B's BUG-1 should count as reopened (its own same-repo "
            "supersedes edge) -- repo A's BUG-1 must not be reopened by "
            "repo B's unrelated FEAT-9 supersedes: [BUG-1]"
        )


class TestFollowUpFixSurvivesDiscriminator:
    """AC: the `#r{i}` suffix (not a prefix) keeps `startswith('BUG-')` matching."""

    def test_follow_up_signal_identical_standalone_and_in_union(self, tmp_path: Path) -> None:
        m1 = _bare_member(tmp_path, "repo_a", "primary")
        m2 = _bare_member(tmp_path, "repo_b", "sibling")

        # repo A: unrelated closed issue in a different month.
        _close(m1.db_path, "BUG-100", "2026-01-01T00:00:00Z")

        # repo B: FEAT-3 closes, then a same-files BUG-4 commit lands within
        # the follow-up window.
        _close(m2.db_path, "FEAT-3", "2026-04-01T00:00:00Z")
        record_commit_event(
            m2.db_path,
            "a" * 40,
            "work on FEAT-3",
            issue_id="FEAT-3",
            files=["src/x.py"],
            ts="2026-04-01T00:00:00Z",
        )
        record_commit_event(
            m2.db_path,
            "b" * 40,
            "fix BUG-4",
            issue_id="BUG-4",
            files=["src/x.py"],
            ts="2026-04-03T00:00:00Z",
        )

        issues_b = [
            IssueInfo(
                path=Path("f3.md"),
                issue_type="features",
                priority="P2",
                issue_id="FEAT-3",
                title="FEAT-3",
            )
        ]
        standalone = analyze_rework(issues_b, db=m2.db_path, min_sample=1)
        standalone_window = next(w for w in standalone.windows if w.period == "2026-04")
        assert standalone_window.follow_up.rate == 1.0, "sanity check on the fixture itself"

        issues_a = [
            IssueInfo(
                path=Path("b100.md"),
                issue_type="bugs",
                priority="P2",
                issue_id="BUG-100",
                title="BUG-100",
            )
        ]
        combined = _discriminate_issues(issues_a, _discriminator(0)) + _discriminate_issues(
            issues_b, _discriminator(1)
        )
        conn = _open_union([m1.db_path, m2.db_path])
        try:
            union_analysis = analyze_rework(combined, conn=conn, min_sample=1)
        finally:
            conn.close()

        union_window = next(w for w in union_analysis.windows if w.period == "2026-04")
        assert union_window.follow_up.rate == standalone_window.follow_up.rate == 1.0


class TestUnionDenominatorNotAveraged:
    """AC: the union rate reflects combined counts, not the mean of per-repo rates."""

    def test_reopen_rate_uses_summed_counts(self, tmp_path: Path) -> None:
        m1 = _bare_member(tmp_path, "repo_a", "primary")
        m2 = _bare_member(tmp_path, "repo_b", "sibling")

        for i in range(3):
            _close(m1.db_path, f"BUG-{i}", "2026-05-01T00:00:00Z")
        _reopen(m1.db_path, "BUG-0", "2026-05-10T00:00:00Z")

        _close(m2.db_path, "BUG-9", "2026-05-01T00:00:00Z")

        result = aggregate_history_dbs(
            [m1, m2], min_sample=1, sensitivity=0.3, baseline_windows=3, latest_only=True
        )

        assert result.totals is not None
        w = next(w for w in result.totals.windows if w.period == "2026-05")
        assert w.closed_count == 4
        # reopen_rate = 1/4 = 0.25 across the union; the per-repo mean of
        # (1/3, 0/1) would be 0.1667 -- fix_rate = 1 - rework_share catches
        # a wrongly-averaged denominator.
        assert w.metrics["fix_rate"].value == pytest.approx(0.75)


class TestFindIssuesCalledOncePerMember:
    """AC: the totals pass reuses the per-member `find_issues()` list; no second call."""

    def test_find_issues_called_exactly_once_per_member(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        m1 = _member_with_closed_issue(tmp_path, "repo_a", "primary", "BUG-1")
        m2 = _member_with_closed_issue(tmp_path, "repo_b", "sibling", "BUG-2")

        calls: list[object] = []
        original = workspace_quality.find_issues

        def counting(*args: object, **kwargs: object) -> list[IssueInfo]:
            calls.append(args)
            return original(*args, **kwargs)

        monkeypatch.setattr(workspace_quality, "find_issues", counting)

        result = aggregate_history_dbs(
            [m1, m2], min_sample=1, sensitivity=0.3, baseline_windows=3, latest_only=True
        )

        assert result.totals is not None
        assert len(calls) == 2


class TestSourceUntouchedDuringTotals:
    def test_member_files_unchanged_after_totals_run(self, tmp_path: Path) -> None:
        import hashlib

        def sha(p: Path) -> str:
            return hashlib.sha256(p.read_bytes()).hexdigest()

        m1 = _member_with_closed_issue(tmp_path, "repo_a", "primary", "BUG-1")
        m2 = _member_with_closed_issue(tmp_path, "repo_b", "sibling", "BUG-2")
        before = {m1.db_path: sha(m1.db_path), m2.db_path: sha(m2.db_path)}

        result = aggregate_history_dbs(
            [m1, m2], min_sample=1, sensitivity=0.3, baseline_windows=3, latest_only=True
        )

        assert result.totals is not None
        for path, digest in before.items():
            assert sha(path) == digest
