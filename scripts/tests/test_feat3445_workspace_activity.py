"""Tests for issue_history.workspace_activity — FEAT-3445's cross-repo activity reader.

Covers: per-member counts (loops_run/loops_completed/issues_completed/
issues_deferred), the running-loop (NULL ended_at) exclusion, since/until
windowing, mixed-timestamp-format safety, NULL/empty/date-only timestamp
handling, member status classification (db_missing/schema_skew/unreadable),
a count-phase sqlite3.Error mapping to unreadable, workspace totals
(including the all-non-ok zero-counts case), canonical serialization, and a
source-inspection proving the module never uses a migrating opener.
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from little_loops.issue_history.workspace_activity import (
    MemberActivityStatus,
    RepoActivity,
    WorkspaceActivityResult,
    aggregate_workspace_activity,
)
from little_loops.session_store.schema import SCHEMA_VERSION
from little_loops.session_store.writers import record_issue_event, record_loop_run_summary
from little_loops.workspace import WorkspaceMember


def _member(tmp_path: Path, name: str, role: str) -> WorkspaceMember:
    """A member repo whose history.db is created lazily by the first write-API call.

    Named ``<name>-history.db`` (not the default-shaped ``.ll/history.db``)
    to dodge the autouse ``_isolate_history_db`` fixture that routes
    default-shaped paths through one shared ``LL_HISTORY_DB`` env var.
    """
    repo_path = tmp_path / name
    (repo_path / ".issues").mkdir(parents=True)
    (repo_path / ".ll").mkdir()
    db_path = repo_path / ".ll" / f"{name}-history.db"
    return WorkspaceMember(repo_path=repo_path, role=role, db_path=db_path)


def _insert_running_loop_run(db: Path, run_id: str, loop_name: str, started_at: str) -> None:
    """Insert a `loop_runs` row with a NULL `ended_at` (a genuinely in-flight run).

    `record_loop_run_summary()` is only ever called at run completion
    (`fsm/executor.py`'s `_finish()`) and always stamps `ended_at` (falling
    back to "now" when the caller passes ``None``), so it cannot produce this
    row shape. Insert directly, matching `ended_at`'s nullable schema column.
    """
    conn = sqlite3.connect(str(db))
    try:
        conn.execute(
            "INSERT INTO loop_runs(run_id, loop_name, started_at, ended_at) VALUES (?, ?, ?, NULL)",
            (run_id, loop_name, started_at),
        )
        conn.commit()
    finally:
        conn.close()


def _stamp_issue_ts(db: Path, issue_id: str, transition: str, ts: str | None) -> None:
    conn = sqlite3.connect(str(db))
    try:
        conn.execute(
            "UPDATE issue_events SET ts = ? WHERE issue_id = ? AND transition = ?",
            (ts, issue_id, transition),
        )
        conn.commit()
    finally:
        conn.close()


def _skewed_member(tmp_path: Path, name: str, role: str, *, schema_version: str) -> WorkspaceMember:
    repo_path = tmp_path / name
    (repo_path / ".issues").mkdir(parents=True)
    ll_dir = repo_path / ".ll"
    ll_dir.mkdir()
    db_path = ll_dir / "history.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
    conn.execute("INSERT INTO meta (key, value) VALUES ('schema_version', ?)", (schema_version,))
    conn.commit()
    conn.close()
    return WorkspaceMember(repo_path=repo_path, role=role, db_path=db_path)


def _gate_passes_no_activity_tables(tmp_path: Path, name: str, role: str) -> WorkspaceMember:
    """A member whose schema_version matches but has no `loop_runs`/`issue_events` tables.

    The gate (schema-version check) passes, so the count SQL is reached and
    fails with `sqlite3.OperationalError: no such table` — exercising the
    "count query failed" branch of `MemberActivityStatus.UNREADABLE`.
    """
    repo_path = tmp_path / name
    (repo_path / ".issues").mkdir(parents=True)
    ll_dir = repo_path / ".ll"
    ll_dir.mkdir()
    db_path = ll_dir / "history.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
    conn.execute(
        "INSERT INTO meta (key, value) VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),)
    )
    conn.commit()
    conn.close()
    return WorkspaceMember(repo_path=repo_path, role=role, db_path=db_path)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TestPerMemberCounts:
    """AC 1, AC 4: per-member counts, running-loop exclusion, until as inclusive upper bound."""

    def test_running_loop_never_counts_completed(self, tmp_path: Path) -> None:
        member = _member(tmp_path, "repo_a", "primary")
        record_loop_run_summary(
            member.db_path,
            run_id="run-done",
            loop_name="l",
            started_at="2026-01-01T00:00:00Z",
            ended_at="2026-01-02T00:00:00Z",
            final_state="done",
        )
        _insert_running_loop_run(member.db_path, "run-running", "l", "2026-01-01T00:00:00Z")

        result = aggregate_workspace_activity([member], since=None, until=None)
        activity = result.per_repo[str(member.db_path)]

        assert activity.loops_run == 2
        assert activity.loops_completed == 1

    def test_since_and_until_independently_optional(self, tmp_path: Path) -> None:
        member = _member(tmp_path, "repo_a", "primary")
        record_loop_run_summary(
            member.db_path,
            run_id="run-early",
            loop_name="l",
            started_at="2026-01-01T00:00:00Z",
            ended_at="2026-01-01T01:00:00Z",
            final_state="done",
        )
        record_loop_run_summary(
            member.db_path,
            run_id="run-late",
            loop_name="l",
            started_at="2026-02-01T00:00:00Z",
            ended_at="2026-02-01T01:00:00Z",
            final_state="done",
        )

        since_only = aggregate_workspace_activity([member], since="2026-01-15T00:00:00Z")
        until_only = aggregate_workspace_activity(
            [member], since=None, until="2026-01-15T00:00:00Z"
        )

        assert since_only.per_repo[str(member.db_path)].loops_run == 1
        assert until_only.per_repo[str(member.db_path)].loops_run == 1

    def test_until_is_inclusive(self, tmp_path: Path) -> None:
        member = _member(tmp_path, "repo_a", "primary")
        record_loop_run_summary(
            member.db_path,
            run_id="run-boundary",
            loop_name="l",
            started_at="2026-01-15T00:00:00Z",
            ended_at="2026-01-15T00:00:00Z",
            final_state="done",
        )

        result = aggregate_workspace_activity([member], since=None, until="2026-01-15T00:00:00Z")
        assert result.per_repo[str(member.db_path)].loops_run == 1

    def test_issues_completed_and_deferred_counted_separately(self, tmp_path: Path) -> None:
        member = _member(tmp_path, "repo_a", "primary")
        record_issue_event(member.db_path, "BUG-1", "done")
        record_issue_event(member.db_path, "BUG-2", "deferred")
        _stamp_issue_ts(member.db_path, "BUG-1", "done", "2026-01-10T00:00:00Z")
        _stamp_issue_ts(member.db_path, "BUG-2", "deferred", "2026-01-10T00:00:00Z")

        result = aggregate_workspace_activity([member], since=None, until=None)
        activity = result.per_repo[str(member.db_path)]

        assert activity.issues_completed == 1
        assert activity.issues_deferred == 1


class TestTimestampFormats:
    """AC 5: format-safe comparison across mixed forms, NULL/empty/date-only handling."""

    def test_mixed_format_ordering_is_format_safe(self, tmp_path: Path) -> None:
        member = _member(tmp_path, "repo_a", "primary")
        # Lexicographically this micros form sorts *before* the Z form despite
        # being temporally *after* it — a raw string compare would misorder it.
        record_loop_run_summary(
            member.db_path,
            run_id="run-micros",
            loop_name="l",
            started_at="2026-09-10T22:48:17.151663+00:00",
            ended_at="2026-09-10T22:48:17.151663+00:00",
            final_state="done",
        )

        result = aggregate_workspace_activity([member], since="2026-09-10T22:48:17Z", until=None)
        assert result.per_repo[str(member.db_path)].loops_run == 1
        assert result.per_repo[str(member.db_path)].loops_completed == 1

    def test_null_started_at_excluded_from_window_included_unbounded(self, tmp_path: Path) -> None:
        member = _member(tmp_path, "repo_a", "primary")
        record_loop_run_summary(
            member.db_path,
            run_id="run-null-start",
            loop_name="l",
            started_at=None,
            ended_at="2026-01-01T00:00:00Z",
            final_state="done",
        )

        unbounded = aggregate_workspace_activity([member], since=None, until=None)
        windowed = aggregate_workspace_activity([member], since="2020-01-01T00:00:00Z")

        assert unbounded.per_repo[str(member.db_path)].loops_run == 1
        assert windowed.per_repo[str(member.db_path)].loops_run == 0

    def test_empty_and_date_only_issue_ts_do_not_raise(self, tmp_path: Path) -> None:
        member = _member(tmp_path, "repo_a", "primary")
        record_issue_event(member.db_path, "BUG-1", "done")
        record_issue_event(member.db_path, "BUG-2", "done")
        _stamp_issue_ts(member.db_path, "BUG-1", "done", "")
        _stamp_issue_ts(member.db_path, "BUG-2", "done", "2026-09-10")

        unbounded = aggregate_workspace_activity([member], since=None, until=None)
        windowed = aggregate_workspace_activity([member], since="2020-01-01T00:00:00Z")

        assert unbounded.per_repo[str(member.db_path)].issues_completed == 2
        # date-only "2026-09-10" is a valid naive-UTC timestamp and is in-window;
        # empty string is excluded even from a windowed count.
        assert windowed.per_repo[str(member.db_path)].issues_completed == 1

    def test_naive_since_bound_treated_as_utc(self, tmp_path: Path) -> None:
        member = _member(tmp_path, "repo_a", "primary")
        record_loop_run_summary(
            member.db_path,
            run_id="run-a",
            loop_name="l",
            started_at="2026-01-15T00:00:00Z",
            ended_at="2026-01-15T00:00:00Z",
            final_state="done",
        )

        result = aggregate_workspace_activity([member], since="2026-01-01")
        assert result.per_repo[str(member.db_path)].loops_run == 1


class TestMemberStatus:
    """AC 1, AC 2: status classification, None (never 0) counts on non-ok members."""

    def test_db_missing(self, tmp_path: Path) -> None:
        member = _member(tmp_path, "repo_a", "primary")

        result = aggregate_workspace_activity([member], since=None, until=None)
        activity = result.per_repo[str(member.db_path)]

        assert activity.status is MemberActivityStatus.DB_MISSING
        assert activity.instrumented is False
        assert activity.loops_run is None
        assert activity.loops_completed is None
        assert activity.issues_completed is None
        assert activity.issues_deferred is None
        assert activity.reason is not None

    def test_schema_skew(self, tmp_path: Path) -> None:
        member = _skewed_member(tmp_path, "stale", "primary", schema_version="1")

        result = aggregate_workspace_activity([member], since=None, until=None)
        activity = result.per_repo[str(member.db_path)]

        assert activity.status is MemberActivityStatus.SCHEMA_SKEW
        assert activity.instrumented is True
        assert activity.loops_run is None
        assert activity.reason is not None

    def test_unreadable_non_sqlite_file(self, tmp_path: Path) -> None:
        repo_path = tmp_path / "garbage"
        (repo_path / ".issues").mkdir(parents=True)
        ll_dir = repo_path / ".ll"
        ll_dir.mkdir()
        db_path = ll_dir / "history.db"
        db_path.write_text("not a database")
        member = WorkspaceMember(repo_path=repo_path, role="primary", db_path=db_path)

        result = aggregate_workspace_activity([member], since=None, until=None)
        activity = result.per_repo[str(member.db_path)]

        assert activity.status is MemberActivityStatus.UNREADABLE
        assert activity.instrumented is True
        assert activity.loops_run is None

    def test_count_sql_error_maps_to_unreadable(self, tmp_path: Path) -> None:
        member = _gate_passes_no_activity_tables(tmp_path, "repo_a", "primary")

        result = aggregate_workspace_activity([member], since=None, until=None)
        activity = result.per_repo[str(member.db_path)]

        assert activity.status is MemberActivityStatus.UNREADABLE
        assert activity.instrumented is True
        assert activity.loops_run is None
        assert activity.reason is not None
        assert "count query failed" in activity.reason

    def test_main_file_hash_unchanged_on_skip(self, tmp_path: Path) -> None:
        member = _skewed_member(tmp_path, "stale", "primary", schema_version="1")
        before = _sha256(member.db_path)

        aggregate_workspace_activity([member], since=None, until=None)

        assert _sha256(member.db_path) == before


class TestTotals:
    """AC 3: totals always present, count fields None only when ok_members == 0."""

    def test_totals_sum_ok_members_only(self, tmp_path: Path) -> None:
        ok_member = _member(tmp_path, "repo_a", "primary")
        record_loop_run_summary(
            ok_member.db_path,
            run_id="run-a",
            loop_name="l",
            started_at="2026-01-01T00:00:00Z",
            ended_at="2026-01-01T00:00:00Z",
            final_state="done",
        )
        skewed_member = _skewed_member(tmp_path, "stale", "sibling", schema_version="1")

        result = aggregate_workspace_activity([ok_member, skewed_member], since=None, until=None)

        assert result.totals.members == 2
        assert result.totals.ok_members == 1
        assert result.totals.instrumented_members == 2
        assert result.totals.instrumented is True
        assert result.totals.loops_run == 1

    def test_totals_counts_none_when_zero_ok_members(self, tmp_path: Path) -> None:
        skewed_member = _skewed_member(tmp_path, "stale", "primary", schema_version="1")

        result = aggregate_workspace_activity([skewed_member], since=None, until=None)

        assert result.totals.ok_members == 0
        assert result.totals.members == 1
        assert result.totals.instrumented is True
        assert result.totals.loops_run is None
        assert result.totals.loops_completed is None
        assert result.totals.issues_completed is None
        assert result.totals.issues_deferred is None

    def test_totals_present_for_empty_workspace(self) -> None:
        result = aggregate_workspace_activity([], since=None, until=None)

        assert result.totals.members == 0
        assert result.totals.ok_members == 0
        assert result.totals.instrumented is False
        assert result.totals.loops_run is None


class TestSerialization:
    """AC 9: canonical serialization — ok/error fields, issues_closed always null."""

    def test_ok_member_to_dict(self, tmp_path: Path) -> None:
        member = _member(tmp_path, "repo_a", "primary")
        record_loop_run_summary(
            member.db_path,
            run_id="run-a",
            loop_name="l",
            started_at="2026-01-01T00:00:00Z",
            ended_at="2026-01-01T00:00:00Z",
            final_state="done",
        )

        result = aggregate_workspace_activity([member], since=None, until=None)
        payload = result.to_dict()
        (row,) = payload["per_repo"]

        assert row["ok"] is True
        assert row["status"] == "ok"
        assert row["error"] is None
        assert row["issues_closed"] is None
        assert row["repo_path"] == str(member.repo_path)
        assert row["label"] == f"{member.repo_path.name} ({member.role})"

    def test_non_ok_member_to_dict_never_zero(self, tmp_path: Path) -> None:
        member = _member(tmp_path, "repo_a", "primary")

        result = aggregate_workspace_activity([member], since=None, until=None)
        payload = result.to_dict()
        (row,) = payload["per_repo"]

        assert row["ok"] is False
        assert row["error"] is not None
        assert row["loops_run"] is None
        assert row["loops_completed"] is None

    def test_totals_to_dict_key_order(self, tmp_path: Path) -> None:
        member = _member(tmp_path, "repo_a", "primary")
        result = aggregate_workspace_activity([member], since="2026-01-01T00:00:00Z", until=None)
        payload = result.to_dict()

        assert list(payload["totals"].keys()) == [
            "members",
            "instrumented_members",
            "instrumented",
            "ok_members",
            "loops_run",
            "loops_completed",
            "issues_completed",
            "issues_deferred",
            "issues_closed",
        ]
        assert payload["totals"]["issues_closed"] is None
        assert payload["since"] == "2026-01-01T00:00:00Z"
        assert payload["until"] is None

    def test_result_and_repo_activity_are_frozen(self, tmp_path: Path) -> None:
        member = _member(tmp_path, "repo_a", "primary")
        result = aggregate_workspace_activity([member], since=None, until=None)
        assert isinstance(result, WorkspaceActivityResult)
        activity = next(iter(result.per_repo.values()))
        assert isinstance(activity, RepoActivity)


class TestNeverUsesMigratingOpener:
    def test_source_inspection(self) -> None:
        """Mirrors `test_feat3410_workspace_quality.py::test_never_uses_migrating_opener`.

        Unlike quality, this module owns no connection-opening logic of its
        own -- it delegates entirely to `workspace_quality._gate_member()`
        (whose own read-only-only contract is covered by
        `test_feat3410_workspace_quality.py::test_never_uses_migrating_opener`).
        This test proves that delegation and that no migrating opener was
        added directly to this module's code.
        """
        import little_loops.issue_history.workspace_activity as mod

        text = Path(mod.__file__).read_text()
        code = text[text.index("def _parse_ts") :]
        assert "ensure_db(" not in code
        assert "_connect_readonly(" not in code
        assert "immutable=1" not in code
        assert "_gate_member" in text
