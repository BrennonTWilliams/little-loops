"""Tests for the shared read-only ``HistorySnapshot`` reader (FEAT-3721).

Fixtures build real SQLite stores; deadline behavior uses a fake monotonic clock
(``deadline.now``) rather than stopwatch bounds, and hooks on the reader's module-level
seams (``_decode_row``, ``_WINDOW_SQL``) inject mid-fetch expiry and failures.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from little_loops.next_arena import history as hist
from little_loops.next_arena.history import (
    RecentSprintInvocations,
    read_history_snapshot,
)
from little_loops.next_arena.recording import project_key_for
from little_loops.session_store import (
    RECOMMENDATION_EVENTS_MIN_VERSION,
    RECOMMENDATION_LOOKUP_SQL,
    SCHEMA_VERSION,
    Deadline,
)
from little_loops.session_store import deadline as deadline_mod
from little_loops.session_store.backend import (
    BackendConfig,
    HistoryUnavailable,
    LocalTarget,
    RemoteTarget,
)
from little_loops.session_store.db import resolve_history_target
from tests.recommendation_support import event_row, insert_row, make_real_store, replace_table

AS_OF = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)
OBSERVED = datetime(2026, 10, 7, 12, 0, 5, tzinfo=UTC)

CLI_DDL = """CREATE TABLE cli_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, binary TEXT NOT NULL,
    args TEXT NOT NULL, exit_code INTEGER, duration_ms INTEGER)"""
COLUMNS = "(id, ts, binary, args, exit_code, duration_ms)"


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> FakeClock:
    fake = FakeClock()
    monkeypatch.setattr(deadline_mod, "now", fake)
    return fake


def args_json(name: str = "alpha") -> str:
    return json.dumps(["run", name])


def make_store(
    path: Path,
    rows: list[tuple[Any, ...]] | None = None,
    ddl: str | None = CLI_DDL,
    wal: bool = False,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    if wal:
        conn.execute("PRAGMA journal_mode=WAL")
    if ddl:
        conn.execute(ddl)
    if rows:
        conn.executemany(f"INSERT INTO cli_events {COLUMNS} VALUES (?,?,?,?,?,?)", rows)
    conn.commit()
    if wal:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.close()
    return path


def sprint_row(i: int, name: str = "alpha", ts: str | None = None) -> tuple[Any, ...]:
    return (i, ts or f"2026-10-01T00:00:{i % 60:02d}Z", "ll-sprint", args_json(name), 0, 10)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    (root / ".ll").mkdir(parents=True)
    return root


def owned(project: Path) -> Path:
    return project / ".ll" / "history.db"


def read(
    path: Path, project: Path, *, names: tuple[str, ...] = ("alpha",), target: Any = None
) -> hist.HistoryReadResult:
    snap = read_history_snapshot(
        target or LocalTarget(path),
        as_of=AS_OF,
        requests=[RecentSprintInvocations(project, names)],
        now=lambda: OBSERVED,
    )
    return snap.results_by_request["sprint_invocations"]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TestRequestValidation:
    def test_empty_requests_open_nothing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def boom(*a: Any, **k: Any) -> None:
            raise AssertionError("opened a store")

        monkeypatch.setattr(hist, "connect_readonly", boom)
        snap = read_history_snapshot(
            LocalTarget(Path("/nonexistent/h.db")), as_of=AS_OF, requests=[], now=lambda: OBSERVED
        )
        assert dict(snap.results_by_request) == {}
        assert snap.read_observed_at is None and snap.as_of == AS_OF and snap.diagnostics == ()

    def test_duplicate_kinds_fail_before_opening(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(hist, "connect_readonly", lambda *a, **k: pytest.fail("opened"))
        req = RecentSprintInvocations(project, ("a",))
        with pytest.raises(ValueError, match="duplicate"):
            read_history_snapshot(
                LocalTarget(owned(project)),
                as_of=AS_OF,
                requests=[req, RecentSprintInvocations(project, ("b",))],
                now=lambda: OBSERVED,
            )

    def test_naive_as_of_and_relative_path_rejected(self, project: Path) -> None:
        req = [RecentSprintInvocations(project)]
        with pytest.raises(ValueError, match="timezone-aware"):
            read_history_snapshot(
                LocalTarget(owned(project)),
                as_of=datetime(2026, 1, 1),
                requests=req,
                now=lambda: OBSERVED,
            )
        with pytest.raises(ValueError, match="absolute"):
            read_history_snapshot(
                LocalTarget(Path(".ll/history.db")), as_of=AS_OF, requests=req, now=lambda: OBSERVED
            )

    def test_remote_target_unsupported_without_connecting(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(hist, "connect_readonly", lambda *a, **k: pytest.fail("connected"))
        remote = RemoteTarget(BackendConfig(provider="libsql", url="libsql://example"))
        result = read(owned(project), project, target=remote)
        assert (result.availability, result.reason) == ("unavailable", "remote_unsupported_v1")
        assert result.diagnostics and result.diagnostics[0].subject == "sprint_invocations"


class TestReadAndProvenance:
    def test_available_read_leaves_store_untouched(self, project: Path) -> None:
        db = make_store(owned(project), [sprint_row(1), sprint_row(2, "beta")])
        before_digest, before_files = digest(db), sorted(p.name for p in db.parent.iterdir())
        snap = read_history_snapshot(
            LocalTarget(db),
            as_of=AS_OF,
            requests=[RecentSprintInvocations(project, ("alpha", "beta"))],
            now=lambda: OBSERVED,
        )
        result = snap.results_by_request["sprint_invocations"]
        assert result.availability == "available" and result.reason is None
        assert [r.id for r in result.rows] == [2, 1] and result.rows[0].args == ("run", "beta")
        cov = result.coverage
        assert cov.reached_start and cov.completed_range == (1, 2) and cov.returned_rows == 2
        assert snap.read_observed_at == OBSERVED and snap.as_of == AS_OF
        assert digest(db) == before_digest
        assert sorted(p.name for p in db.parent.iterdir()) == before_files

    def test_wal_store_main_db_unchanged(self, project: Path) -> None:
        db = make_store(owned(project), [sprint_row(1)], wal=True)
        before = digest(db)
        assert read(db, project).availability == "available"
        assert digest(db) == before
        extras = {p.name for p in db.parent.iterdir()} - {db.name}
        assert extras <= {f"{db.name}-wal", f"{db.name}-shm"}  # SQLite-managed sidecars only

    def test_empty_table_available_and_missing_file_unavailable(self, project: Path) -> None:
        empty = read(make_store(owned(project)), project)
        assert (
            empty.availability == "available" and empty.rows == () and empty.coverage.reached_start
        )
        missing = project / "elsewhere" / "h.db"
        result = read(missing, project)
        assert (result.availability, result.reason) == ("unavailable", "store_missing")
        assert not missing.exists() and not missing.parent.exists()

    def test_missing_table_unavailable_with_unset_observation(self, project: Path) -> None:
        db = make_store(owned(project), ddl="CREATE TABLE other(a)")
        snap = read_history_snapshot(
            LocalTarget(db),
            as_of=AS_OF,
            requests=[RecentSprintInvocations(project)],
            now=lambda: OBSERVED,
        )
        assert snap.results_by_request["sprint_invocations"].reason == "missing_table"
        assert snap.read_observed_at == OBSERVED  # the metadata read established the snapshot

    def test_missing_store_has_no_observation(self, project: Path) -> None:
        snap = read_history_snapshot(
            LocalTarget(owned(project)),
            as_of=AS_OF,
            requests=[RecentSprintInvocations(project)],
            now=lambda: OBSERVED,
        )
        assert snap.read_observed_at is None

    def test_connection_options_and_cleanup(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db = make_store(owned(project), [sprint_row(1)])
        seen: dict[str, Any] = {}
        real = hist.connect_readonly

        def spy(target: Any, **kwargs: Any) -> sqlite3.Connection:
            seen.update(kwargs)
            seen["conn"] = real(target, **kwargs)
            return seen["conn"]  # type: ignore[no-any-return]

        monkeypatch.setattr(hist, "connect_readonly", spy)
        read(db, project)
        assert seen["timeout"] == 0.25 and isinstance(seen["deadline"], Deadline)
        with pytest.raises(sqlite3.ProgrammingError):
            seen["conn"].execute("select 1")

    def test_old_schema_without_autoincrement_and_extra_columns(self, project: Path) -> None:
        ddl = (
            "CREATE TABLE cli_events (id integer primary key, ts TEXT, binary TEXT, args TEXT,"
            " exit_code INTEGER, duration_ms INTEGER, extra TEXT)"
        )
        db = make_store(owned(project), [sprint_row(1)], ddl=ddl)
        assert read(db, project).availability == "available"

    def test_out_of_order_timestamps_are_not_trusted_by_id(self, project: Path) -> None:
        rows = [sprint_row(1, ts="2026-10-05T00:00:00Z"), sprint_row(2, ts="2026-09-01T00:00:00Z")]
        result = read(make_store(owned(project), rows), project)
        # the highest ID is *not* the newest by time; both are returned for the consumer
        assert [(r.id, r.ts) for r in result.rows] == [
            (2, "2026-09-01T00:00:00Z"),
            (1, "2026-10-05T00:00:00Z"),
        ]


SPECIAL_NAMES = ["hash#name.db", "query?name.db", "percent%23name.db", "sp ace.db", "üñí.db"]


class TestLiteralPaths:
    @pytest.mark.parametrize("name", SPECIAL_NAMES)
    def test_existing_special_path_identifies_intended_file(self, project: Path, name: str) -> None:
        owned_db = make_store(owned(project), [sprint_row(1)])
        special = make_store(project / name, [sprint_row(9)])
        # decoy aliases a truncated/decoded URI would open instead (no cli_events table)
        for alias in ("hash", "query", "percent#name.db", "sp", "percent%name.db"):
            make_store(project / alias, ddl="CREATE TABLE decoy(a)")
        # an unscoped store is partial(unscoped_store): the shape probe reached the *right* file
        result = read(special, project)
        assert (result.availability, result.reason) == ("partial", "unscoped_store")
        assert result.rows == ()
        assert read(owned_db, project).availability == "available"

    @pytest.mark.parametrize("name", SPECIAL_NAMES)
    def test_missing_special_path_creates_nothing(self, project: Path, name: str) -> None:
        before = sorted(p.name for p in project.rglob("*"))
        result = read(project / name, project)
        assert (result.availability, result.reason) == ("unavailable", "store_missing")
        assert sorted(p.name for p in project.rglob("*")) == before


class TestOwnership:
    def test_symlinked_database_is_unscoped(self, project: Path, tmp_path: Path) -> None:
        external = make_store(tmp_path / "shared" / "h.db", [sprint_row(1)])
        owned(project).symlink_to(external)
        result = read(owned(project), project)
        assert (result.availability, result.reason) == ("partial", "unscoped_store")
        assert result.rows == ()

    def test_symlinked_ll_directory_is_unscoped(self, tmp_path: Path) -> None:
        root = tmp_path / "proj2"
        root.mkdir()
        make_store(tmp_path / "ext_ll" / "history.db", [sprint_row(1)])
        (root / ".ll").symlink_to(tmp_path / "ext_ll")
        result = read(root / ".ll" / "history.db", root)
        assert result.reason == "unscoped_store"

    def test_alias_of_owned_store_is_scoped(self, project: Path, tmp_path: Path) -> None:
        db = make_store(owned(project), [sprint_row(1)])
        alias_root = tmp_path / "alias_root"
        alias_root.symlink_to(project)
        assert read(alias_root / ".ll" / "history.db", project).availability == "available"
        assert read(db, alias_root).availability == "available"

    def test_other_path_is_unscoped(self, project: Path) -> None:
        other = make_store(project / "other.db", [sprint_row(1)])
        assert read(other, project).reason == "unscoped_store"


LOOKALIKES = {
    "no_key": "CREATE TABLE cli_events (id INTEGER, ts TEXT, binary TEXT, args TEXT, exit_code INTEGER, duration_ms INTEGER)",
    "text_key": "CREATE TABLE cli_events (id TEXT PRIMARY KEY, ts TEXT, binary TEXT, args TEXT, exit_code INTEGER, duration_ms INTEGER)",
    "int_key": "CREATE TABLE cli_events (id INT PRIMARY KEY, ts TEXT, binary TEXT, args TEXT, exit_code INTEGER, duration_ms INTEGER)",
    "composite": "CREATE TABLE cli_events (id INTEGER, ts TEXT, binary TEXT, args TEXT, exit_code INTEGER, duration_ms INTEGER, PRIMARY KEY (id, ts))",
    "desc_key": "CREATE TABLE cli_events (id INTEGER PRIMARY KEY DESC, ts TEXT, binary TEXT, args TEXT, exit_code INTEGER, duration_ms INTEGER)",
    "without_rowid": "CREATE TABLE cli_events (id INTEGER PRIMARY KEY, ts TEXT, binary TEXT, args TEXT, exit_code INTEGER, duration_ms INTEGER) WITHOUT ROWID",
    "missing_column": "CREATE TABLE cli_events (id INTEGER PRIMARY KEY, ts TEXT, binary TEXT, args TEXT)",
}


class TestSourceShape:
    @pytest.mark.parametrize("shape", sorted(LOOKALIKES))
    def test_lookalike_rejected_before_activity_sql(
        self, project: Path, shape: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(hist, "_MAX_ID_SQL", "SELECT raise_if_run FROM nope")
        monkeypatch.setattr(hist, "_WINDOW_SQL", "SELECT raise_if_run FROM nope")
        db = make_store(owned(project), ddl=LOOKALIKES[shape])
        result = read(db, project)
        assert (result.availability, result.reason) == ("unavailable", "incompatible_source_shape")

    def test_view_rejected(self, project: Path) -> None:
        db = make_store(
            owned(project),
            ddl="CREATE TABLE real_events (id INTEGER PRIMARY KEY, ts, binary, args, exit_code, duration_ms)",
        )
        conn = sqlite3.connect(db)
        conn.execute("CREATE VIEW cli_events AS SELECT * FROM real_events")
        conn.commit()
        conn.close()
        assert read(db, project).reason == "incompatible_source_shape"

    def test_virtual_table_rejected(self, project: Path) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            conn.execute("CREATE VIRTUAL TABLE t USING fts5(a)")
        except sqlite3.OperationalError:
            pytest.skip("fts5 unavailable")
        conn.close()
        db = make_store(
            owned(project),
            ddl="CREATE VIRTUAL TABLE cli_events USING fts5(id, ts, binary, args, exit_code, duration_ms)",
        )
        assert read(db, project).reason == "incompatible_source_shape"

    def test_one_incompatible_source_does_not_leak_into_other_projects_view(
        self, project: Path
    ) -> None:
        db = make_store(owned(project), [sprint_row(1)], ddl=CLI_DDL.replace(" AUTOINCREMENT", ""))
        assert read(db, project).availability == "available"  # plain rowid alias is valid

    @pytest.mark.parametrize("indexed", [False, True])
    def test_query_plans_use_integer_primary_key_without_sort(
        self, project: Path, indexed: bool
    ) -> None:
        db = make_store(owned(project), [sprint_row(i) for i in range(1, 50)])
        conn = sqlite3.connect(db)
        if indexed:
            conn.execute("CREATE INDEX idx_cli_binary_ts ON cli_events(binary, ts)")
        for sql, params in ((hist._MAX_ID_SQL, ()), (hist._WINDOW_SQL, (1, 200, 10))):
            plan = " | ".join(r[3] for r in conn.execute(f"EXPLAIN QUERY PLAN {sql}", params))
            assert "SEARCH" in plan and "SCAN" not in plan, plan
            if sql is hist._WINDOW_SQL:
                assert "INTEGER PRIMARY KEY" in plan, plan
            assert "idx_cli_binary_ts" not in plan and "TEMP B-TREE" not in plan, plan
        conn.close()
        assert read(db, project).availability == "available"  # compatible index not rejected


class TestBounds:
    def make_big(self, project: Path, count: int, match_every: int, indexed: bool) -> Path:
        rows = [
            (
                i,
                "2026-10-01T00:00:00Z",
                "ll-sprint" if i % match_every == 0 else "ll-auto",
                args_json(),
                0,
                1,
            )
            for i in range(1, count + 1)
        ]
        db = make_store(owned(project), rows)
        if indexed:
            conn = sqlite3.connect(db)
            conn.execute("CREATE INDEX idx_cli_binary_ts ON cli_events(binary, ts)")
            conn.commit()
            conn.close()
        return db

    @pytest.mark.parametrize("indexed", [False, True])
    def test_id_span_cap_is_partial_with_bounded_visits(self, project: Path, indexed: bool) -> None:
        result = read(self.make_big(project, 60_000, 100, indexed), project)
        cov = result.coverage
        assert (result.availability, result.reason) == ("partial", "id_span_cap")
        assert cov.visited_rows_upper_bound == hist.MAX_ID_SPAN and not cov.reached_start
        assert cov.completed_range == (60_000 - hist.MAX_ID_SPAN + 1, 60_000)
        assert len(result.rows) == 500 and all(r.id > 10_000 for r in result.rows)

    @pytest.mark.parametrize("indexed", [False, True])
    def test_returned_row_cap_is_partial(self, project: Path, indexed: bool) -> None:
        result = read(self.make_big(project, 30_000, 1, indexed), project)
        cov = result.coverage
        assert (result.availability, result.reason) == ("partial", "row_cap")
        assert len(result.rows) == cov.returned_rows == hist.MAX_ROWS
        assert cov.visited_rows_upper_bound <= hist.MAX_ID_SPAN
        assert cov.completed_range is not None and not cov.reached_start
        assert result.rows[0].id == 30_000 and result.rows[-1].id == cov.completed_range[0]

    def test_small_store_complete_reaches_start(self, project: Path) -> None:
        result = read(self.make_big(project, 1_000, 10, False), project)
        assert result.availability == "available" and len(result.rows) == 100
        assert result.coverage.completed_range == (1, 1_000) and result.coverage.reached_start

    def test_sparse_ids_advance_by_range_boundary(self, project: Path) -> None:
        db = make_store(owned(project), [sprint_row(1), sprint_row(10_000)])
        result = read(db, project)
        assert result.availability == "available" and [r.id for r in result.rows] == [10_000, 1]
        assert result.coverage.visited_rows_upper_bound == 10_000


class TestPayloadAndMalformed:
    def test_oversized_args_never_decoded(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        huge = json.dumps(["x" * (3 * 1024 * 1024)])
        rows = [sprint_row(1), (2, "2026-10-01T00:00:00Z", "ll-sprint", huge, 0, 1), sprint_row(3)]
        decoded_sizes: list[int] = []
        real_loads = json.loads

        def spy(s: Any, *a: Any, **k: Any) -> Any:
            decoded_sizes.append(len(s))
            return real_loads(s, *a, **k)

        monkeypatch.setattr(hist.json, "loads", spy)
        result = read(make_store(owned(project), rows), project)
        assert (result.availability, result.reason) == ("partial", "payload_limit")
        assert [r.id for r in result.rows] == [3, 1] and result.coverage.skipped_oversized == 1
        assert max(decoded_sizes) < hist.MAX_ARGS_BYTES
        assert result.coverage.payload_bytes == sum(len(args_json()) for _ in result.rows)

    def test_malformed_rows_skipped_with_counts(self, project: Path) -> None:
        rows = [
            sprint_row(1),
            (2, "t", "ll-sprint", "{not json", 0, 1),
            (3, "t", "ll-sprint", '{"a": 1}', 0, 1),
            (4, "t", "ll-sprint", "[1, 2]", 0, 1),
            sprint_row(5),
        ]
        result = read(make_store(owned(project), rows), project)
        assert (result.availability, result.reason) == ("partial", "malformed_row")
        assert [r.id for r in result.rows] == [5, 1] and result.coverage.skipped_malformed == 3
        assert result.coverage.reached_start

    def test_null_duration_is_ordinary_unfinished_evidence(self, project: Path) -> None:
        row = (1, "t", "ll-sprint", args_json(), None, None)
        result = read(make_store(owned(project), [row]), project)
        assert result.availability == "available" and result.rows[0].duration_ms is None

    def test_unexpected_decoder_error_discards_rows(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = {"n": 0}
        real = hist._decode_row

        def flaky(row: Any) -> Any:
            calls["n"] += 1
            if calls["n"] == 2:
                raise KeyError("bug")
            return real(row)

        monkeypatch.setattr(hist, "_decode_row", flaky)
        db = make_store(owned(project), [sprint_row(i) for i in range(1, 5)])
        result = read(db, project)
        assert (result.availability, result.reason) == ("unavailable", "unexpected_error")
        assert result.rows == ()


class TestDeadline:
    def test_expiry_after_metadata_blocks_activity_statements(
        self, project: Path, clock: FakeClock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(hist, "_WINDOW_SQL", "SELECT raise_if_run FROM nope")
        db = make_store(owned(project), [sprint_row(1)])

        def now() -> datetime:
            clock.t = 5.0  # the first read establishes the snapshot, then the budget is gone
            return OBSERVED

        snap = read_history_snapshot(
            LocalTarget(db), as_of=AS_OF, requests=[RecentSprintInvocations(project)], now=now
        )
        result = snap.results_by_request["sprint_invocations"]
        assert (result.availability, result.reason) == ("unavailable", "deadline_exhausted")
        assert snap.read_observed_at == OBSERVED

    def test_expiry_during_open_is_deadline_exhausted(
        self, project: Path, clock: FakeClock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db = make_store(owned(project), [sprint_row(1)])
        real = hist.connect_readonly

        def slow_open(target: Any, **kwargs: Any) -> sqlite3.Connection:
            conn = real(target, **kwargs)
            clock.t = 5.0
            return conn

        monkeypatch.setattr(hist, "connect_readonly", slow_open)
        snap = read_history_snapshot(
            LocalTarget(db),
            as_of=AS_OF,
            requests=[RecentSprintInvocations(project)],
            now=lambda: OBSERVED,
        )
        result = snap.results_by_request["sprint_invocations"]
        assert (result.availability, result.reason) == ("unavailable", "deadline_exhausted")
        assert snap.read_observed_at is None

    def expire_on(self, clock: FakeClock, monkeypatch: pytest.MonkeyPatch, row_id: int) -> None:
        real = hist._decode_row

        def decode(row: Any) -> Any:
            out = real(row)
            if row["id"] == row_id:
                clock.t = 5.0  # budget exhausted right after this row decodes
            return out

        monkeypatch.setattr(hist, "_decode_row", decode)

    def test_mid_decode_expiry_keeps_only_complete_rows(
        self, project: Path, clock: FakeClock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db = make_store(owned(project), [sprint_row(i) for i in range(1, 11)])
        self.expire_on(clock, monkeypatch, 8)
        result = read(db, project)
        cov = result.coverage
        assert (result.availability, result.reason) == ("partial", "deadline")
        assert [r.id for r in result.rows] == [10, 9, 8]
        assert cov.completed_range is None and cov.attempted_range == (1, 10)
        assert cov.visited_rows_upper_bound == 10 and not cov.reached_start

    def test_expiry_between_pages_excludes_interrupted_range(
        self, project: Path, clock: FakeClock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db = make_store(owned(project), [sprint_row(i) for i in range(1, 401)])
        self.expire_on(
            clock, monkeypatch, 150
        )  # inside the second page (IDs 1-200; the first covers 201-400)
        result = read(db, project)
        cov = result.coverage
        assert (result.availability, result.reason) == ("partial", "deadline")
        assert cov.completed_range == (201, 400) and cov.attempted_range == (1, 200)
        assert cov.visited_rows_upper_bound == 400
        assert [r.id for r in result.rows][-1] == 150 and len(result.rows) == 251

    def test_concurrent_writer_does_not_change_snapshot(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db = make_store(owned(project), [sprint_row(i) for i in range(1, 4)], wal=True)
        real = hist._decode_row
        state = {"wrote": False}

        def decode(row: Any) -> Any:
            if not state["wrote"]:
                state["wrote"] = True
                writer = sqlite3.connect(db)
                writer.execute(
                    f"INSERT INTO cli_events {COLUMNS} VALUES (?,?,?,?,?,?)", sprint_row(99)
                )
                writer.commit()
                writer.close()
            return real(row)

        monkeypatch.setattr(hist, "_decode_row", decode)
        result = read(db, project)
        assert state["wrote"] and [r.id for r in result.rows] == [3, 2, 1]
        assert read(db, project).rows[0].id == 99  # a later read observes the new row


class TestFailures:
    def test_non_deadline_query_error_discards_request_rows(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # the second page (IDs below 201) raises "integer overflow"; the first decoded fine
        guarded = hist._WINDOW_SQL.replace(
            "binary = 'll-sprint'",
            "binary = 'll-sprint' AND (id > 200 OR abs(-9223372036854775808) > 0)",
        )
        monkeypatch.setattr(hist, "_WINDOW_SQL", guarded)
        db = make_store(owned(project), [sprint_row(i) for i in range(1, 401)])
        result = read(db, project)
        assert (result.availability, result.reason) == ("unavailable", "query_failed")
        assert result.rows == ()

    def test_locked_store_is_unavailable_not_exception(self, project: Path) -> None:
        db = make_store(owned(project), [sprint_row(1)])
        locker = sqlite3.connect(db, isolation_level=None)
        locker.execute("BEGIN EXCLUSIVE")
        try:
            result = read(db, project)
        finally:
            locker.execute("ROLLBACK")
            locker.close()
        assert result.availability == "unavailable"
        assert result.reason in {"lock_timeout", "store_unavailable", "query_failed"}
        assert read(db, project).availability == "available"

    def test_non_sqlite_file_is_unavailable(self, project: Path) -> None:
        owned(project).write_bytes(b"not a database" * 100)
        assert read(owned(project), project).availability == "unavailable"

    def test_historyunavailable_from_open_is_reported(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def suppressed(*a: Any, **k: Any) -> None:
            raise HistoryUnavailable("suppressed")

        monkeypatch.setattr(hist, "connect_readonly", suppressed)
        make_store(owned(project))
        result = read(owned(project), project)
        assert (result.availability, result.reason) == ("unavailable", "store_unavailable")


class TestResolverIntegration:
    def test_relative_env_override_is_cwd_relative_and_frozen_target_survives_cwd_change(
        self, project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db = make_store(owned(project), [sprint_row(1)])
        sub = project / "pkg" / "sub"
        sub.mkdir(parents=True)
        monkeypatch.setenv("LL_HISTORY_DB", ".ll/history.db")

        monkeypatch.chdir(project)
        from_root = resolve_history_target(None, root=project)
        assert isinstance(from_root, LocalTarget) and not from_root.path.is_absolute()
        frozen = LocalTarget(from_root.path.absolute())

        monkeypatch.chdir(sub)  # later cwd change must not re-resolve the frozen target
        assert read(frozen.path, project, target=frozen).availability == "available"
        from_sub = resolve_history_target(None, root=project)
        assert isinstance(from_sub, LocalTarget)
        # documented exception: the relative override stays cwd-relative from a subdirectory
        assert from_sub.path.absolute() == sub / ".ll" / "history.db" != db

    def test_config_and_default_paths_are_root_relative(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("LL_HISTORY_DB", raising=False)
        sub = project / "pkg"
        sub.mkdir()
        monkeypatch.chdir(sub)
        default = resolve_history_target(None, root=project)
        assert isinstance(default, LocalTarget) and default.path == owned(project)
        (project / ".ll" / "ll-config.json").write_text(
            json.dumps({"history": {"db_path": "data/h.db"}}), encoding="utf-8"
        )
        configured = resolve_history_target(None, root=project)
        assert isinstance(configured, LocalTarget)
        assert configured.path.absolute() == project / "data" / "h.db" or configured.path == (
            project / "data" / "h.db"
        )


def test_core_modules_do_not_import_the_reader() -> None:
    code = (
        "import sys, little_loops.cli.next, little_loops.next_arena.state;"
        "assert 'little_loops.next_arena.history' not in sys.modules"
    )
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


# ------------------------------------------------------------------------------ FEAT-3711
# Real recommendation_lookup / recommendation_schema request kinds over migrated stores.


class TestRecommendationRequests:
    @staticmethod
    def snap(path: Path, project: Path, *requests: Any, target: Any = None) -> hist.HistorySnapshot:
        return read_history_snapshot(
            target or LocalTarget(path),
            as_of=AS_OF,
            requests=list(requests),
            now=lambda: OBSERVED,
        )

    @staticmethod
    def lookup(rec_id: str, root: Path) -> hist.RecommendationLookup:
        return hist.RecommendationLookup(project_key=project_key_for(root), rec_id=rec_id)

    def test_lookup_returns_the_projects_rows_only(self, project: Path) -> None:
        db = make_real_store(owned(project))
        shown = event_row(project)
        insert_row(db, shown)
        insert_row(db, event_row(project, rec_id=shown["rec_id"], kind="accepted_explicit"))
        insert_row(db, event_row(project))  # another offer of this project: not requested
        foreign = event_row("/elsewhere")
        insert_row(db, foreign)
        snap = self.snap(db, project, self.lookup(shown["rec_id"], project))
        result = snap.results_by_request["recommendation_lookup"]
        assert result.availability == "available"
        assert sorted(r.kind for r in result.rows) == ["accepted_explicit", "shown"]
        assert {r.project_key for r in result.rows} == {project_key_for(project)}
        assert result.coverage.returned_rows == 2
        # the identity exists globally, but is not this project's: no rows
        other = self.snap(db, project, self.lookup(foreign["rec_id"], project))
        assert other.results_by_request["recommendation_lookup"].rows == ()

    def test_foreign_project_and_absent_id_are_indistinguishable(self, project: Path) -> None:
        db = make_real_store(owned(project))
        foreign = event_row("/elsewhere")
        insert_row(db, foreign)
        absent = str(uuid.uuid4())
        a = self.snap(db, project, self.lookup(foreign["rec_id"], project))
        b = self.snap(db, project, self.lookup(absent, project))
        assert a.results_by_request["recommendation_lookup"].rows == ()
        assert (
            a.results_by_request["recommendation_lookup"].availability
            == b.results_by_request["recommendation_lookup"].availability
            == "available"
        )

    def test_schema_probe_reports_write_ready_on_a_current_store(self, project: Path) -> None:
        db = make_real_store(owned(project))
        status = (
            self.snap(db, project, hist.RecommendationSchemaProbe())
            .results_by_request["recommendation_schema"]
            .schema_status
        )
        assert status is not None
        assert (status.write_ready, status.read_compatible, status.reason) == (True, True, None)
        assert status.stamp == SCHEMA_VERSION

    @pytest.mark.parametrize("stamp", [RECOMMENDATION_EVENTS_MIN_VERSION - 1, SCHEMA_VERSION + 1])
    def test_older_or_newer_stamp_blocks_writes_but_not_reads(
        self, project: Path, stamp: int
    ) -> None:
        db = make_real_store(owned(project))
        row = event_row(project)
        insert_row(db, row)
        conn = sqlite3.connect(db)
        conn.execute("UPDATE meta SET value = ? WHERE key = 'schema_version'", (str(stamp),))
        conn.commit()
        conn.close()
        snap = self.snap(
            db, project, self.lookup(row["rec_id"], project), hist.RecommendationSchemaProbe()
        )
        status = snap.results_by_request["recommendation_schema"].schema_status
        assert status is not None and status.stamp == stamp
        assert (status.write_ready, status.read_compatible) == (False, True)
        assert status.reason == "schema_not_ready"
        lookup = snap.results_by_request["recommendation_lookup"]
        assert lookup.availability == "available" and len(lookup.rows) == 1

    @pytest.mark.parametrize(
        ("name", "reason"),
        [
            ("partial", "incompatible_index"),
            ("expression", "incompatible_index"),
            ("wrong_key", "incompatible_index"),
            ("nocase", "incompatible_index"),
            ("view", "incompatible_table"),
            ("missing", "missing_table"),
        ],
    )
    def test_lookalikes_are_rejected_before_identity_data_is_queried(
        self, project: Path, name: str, reason: str
    ) -> None:
        db = make_real_store(owned(project))
        variants: dict[str, dict[str, Any]] = {
            "partial": {
                "ddl_tail": "",
                "extra": (
                    "CREATE UNIQUE INDEX u ON recommendation_events(rec_id, kind) WHERE rank >= 1",
                ),
            },
            "expression": {
                "ddl_tail": "",
                "extra": ("CREATE UNIQUE INDEX u ON recommendation_events(lower(rec_id), kind)",),
            },
            "wrong_key": {
                "ddl_tail": "",
                "extra": ("CREATE UNIQUE INDEX u ON recommendation_events(kind, rec_id)",),
            },
            "nocase": {
                "ddl_tail": "",
                "extra": (
                    "CREATE UNIQUE INDEX u ON recommendation_events"
                    "(rec_id COLLATE NOCASE, kind COLLATE NOCASE)",
                ),
            },
        }
        if name in variants:
            replace_table(db, **variants[name])
        elif name == "view":
            conn = sqlite3.connect(db)
            conn.execute("DROP TABLE recommendation_events")
            conn.execute("CREATE TABLE real_events AS SELECT 1 AS rec_id")
            conn.execute("CREATE VIEW recommendation_events AS SELECT * FROM real_events")
            conn.commit()
            conn.close()
        else:
            conn = sqlite3.connect(db)
            conn.execute("DROP TABLE recommendation_events")
            conn.commit()
            conn.close()
        snap = self.snap(
            db, project, self.lookup(str(uuid.uuid4()), project), hist.RecommendationSchemaProbe()
        )
        lookup = snap.results_by_request["recommendation_lookup"]
        assert (lookup.availability, lookup.reason) == ("unavailable", reason)
        status = snap.results_by_request["recommendation_schema"].schema_status
        assert status is not None
        assert (status.write_ready, status.read_compatible, status.reason) == (False, False, reason)

    def test_malformed_shape_leaves_cli_evidence_intact(self, project: Path) -> None:
        db = make_real_store(owned(project))
        conn = sqlite3.connect(db)
        conn.executemany(f"INSERT INTO cli_events {COLUMNS} VALUES (?,?,?,?,?,?)", [sprint_row(1)])
        conn.execute("DROP TABLE recommendation_events")
        conn.commit()
        conn.close()
        snap = self.snap(
            db,
            project,
            RecentSprintInvocations(project, ("alpha",)),
            self.lookup(str(uuid.uuid4()), project),
            hist.RecommendationSchemaProbe(),
        )
        assert snap.results_by_request["sprint_invocations"].availability == "available"
        assert len(snap.results_by_request["sprint_invocations"].rows) == 1
        assert snap.results_by_request["recommendation_lookup"].availability == "unavailable"
        assert snap.results_by_request["recommendation_schema"].availability == "available"

    def test_two_kinds_share_one_snapshot_with_independent_slots(self, project: Path) -> None:
        db = make_real_store(owned(project))
        row = event_row(project)
        insert_row(db, row)
        snap = self.snap(
            db, project, self.lookup(row["rec_id"], project), hist.RecommendationSchemaProbe()
        )
        assert set(snap.results_by_request) == {"recommendation_lookup", "recommendation_schema"}
        lookup = snap.results_by_request["recommendation_lookup"]
        schema = snap.results_by_request["recommendation_schema"]
        assert lookup.schema_status is None and schema.rows == ()
        assert lookup.coverage.returned_rows == 1 and schema.coverage.returned_rows == 0
        assert snap.read_observed_at == OBSERVED

    def test_duplicate_kinds_rejected_before_opening(self, project: Path) -> None:
        missing = LocalTarget(owned(project))  # never created: opening would report unavailable
        with pytest.raises(ValueError, match="duplicate"):
            self.snap(
                missing.path,
                project,
                hist.RecommendationSchemaProbe(),
                hist.RecommendationSchemaProbe(),
            )
        assert not missing.path.exists()

    def test_remote_target_gives_every_requested_kind_one_reason(self, project: Path) -> None:
        cfg = BackendConfig(provider="turso", url="https://example.invalid", project_id="p")
        snap = self.snap(
            owned(project),
            project,
            self.lookup(str(uuid.uuid4()), project),
            hist.RecommendationSchemaProbe(),
            target=RemoteTarget(cfg),
        )
        reasons = {k: r.reason for k, r in snap.results_by_request.items()}
        assert reasons == {
            "recommendation_lookup": "remote_unsupported_v1",
            "recommendation_schema": "remote_unsupported_v1",
        }

    def test_request_local_error_preserves_the_other_result(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db = make_real_store(owned(project))
        row = event_row(project)
        insert_row(db, row)

        def boom(*_a: Any, **_k: Any) -> Any:
            raise RuntimeError("probe bug")

        monkeypatch.setattr(hist, "_read_recommendation_schema", boom)
        snap = self.snap(
            db, project, self.lookup(row["rec_id"], project), hist.RecommendationSchemaProbe()
        )
        assert snap.results_by_request["recommendation_schema"].reason == "unexpected_error"
        assert snap.results_by_request["recommendation_lookup"].availability == "available"

    def test_expiry_marks_unstarted_requests_unavailable_without_statements(
        self, project: Path, clock: FakeClock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db = make_real_store(owned(project))
        row = event_row(project)
        insert_row(db, row)
        real = hist._read_recommendation_lookup

        def expire_after(session: Any, request: Any) -> Any:
            result = real(session, request)
            clock.t = 5.0  # the shared one-second deadline is now spent
            return result

        statements: list[str] = []
        monkeypatch.setattr(hist, "_read_recommendation_lookup", expire_after)
        monkeypatch.setattr(
            hist,
            "_read_recommendation_schema",
            lambda *a, **k: statements.append("ran") or hist.HistoryReadResult("available"),
        )
        snap = self.snap(
            db, project, self.lookup(row["rec_id"], project), hist.RecommendationSchemaProbe()
        )
        assert snap.results_by_request["recommendation_lookup"].availability == "available"
        late = snap.results_by_request["recommendation_schema"]
        assert (late.availability, late.reason) == ("unavailable", "deadline_exhausted")
        assert statements == []

    def test_lookup_transfers_at_most_two_rows_even_with_other_kinds(self, project: Path) -> None:
        db = make_real_store(owned(project))
        rec = str(uuid.uuid4())
        # a newer store may hold more kinds: lift the CHECK and add a third kind for this id
        replace_table(db, ddl_tail="UNIQUE (rec_id, kind)")
        for kind in ("shown", "accepted_explicit", "future_kind"):
            insert_row(db, event_row(project, rec_id=rec, kind=kind))
        result = self.snap(db, project, self.lookup(rec, project)).results_by_request[
            "recommendation_lookup"
        ]
        assert sorted(r.kind for r in result.rows) == ["accepted_explicit", "shown"]

    @pytest.mark.parametrize("declared", ["TEXT", "TEXT COLLATE NOCASE"])
    def test_lookup_plan_is_an_indexed_seek_without_sorting(
        self, project: Path, declared: str
    ) -> None:
        db = make_real_store(owned(project))
        if declared != "TEXT":  # NOCASE-declared identity columns beside a BINARY identity index
            replace_table(
                db,
                ddl_tail="UNIQUE (rec_id, kind)",
                rec=declared,
                kind=declared,
                pk=declared,
                extra=(
                    "CREATE UNIQUE INDEX uq_bin ON recommendation_events"
                    "(rec_id COLLATE BINARY, kind COLLATE BINARY)",
                ),
            )
        conn = sqlite3.connect(db)
        plan = " ".join(
            str(r[3])
            for r in conn.execute("EXPLAIN QUERY PLAN " + RECOMMENDATION_LOOKUP_SQL, ("a", "b"))
        )
        conn.close()
        assert "USING INDEX" in plan and "SCAN" not in plan and "TEMP B-TREE" not in plan
        row = event_row(project)
        insert_row(db, row)
        result = self.snap(db, project, self.lookup(row["rec_id"], project)).results_by_request[
            "recommendation_lookup"
        ]
        assert result.availability == "available" and len(result.rows) == 1

    def test_malformed_stored_value_makes_only_the_lookup_unavailable(self, project: Path) -> None:
        db = make_real_store(owned(project))
        row = event_row(project)
        insert_row(db, row)
        conn = sqlite3.connect(db)
        conn.execute("UPDATE recommendation_events SET rank = 'x' WHERE 1")
        conn.commit()
        conn.close()
        snap = self.snap(
            db, project, self.lookup(row["rec_id"], project), hist.RecommendationSchemaProbe()
        )
        assert snap.results_by_request["recommendation_lookup"].reason == "malformed_event"
        assert snap.results_by_request["recommendation_schema"].availability == "available"

    def test_lookup_leaves_the_main_database_untouched(self, project: Path) -> None:
        db = make_real_store(owned(project))
        row = event_row(project)
        insert_row(db, row)
        before = digest(db)
        self.snap(
            db, project, self.lookup(row["rec_id"], project), hist.RecommendationSchemaProbe()
        )
        assert digest(db) == before
