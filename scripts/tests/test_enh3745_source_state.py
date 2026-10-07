"""ENH-3745 phase 2: the five-table source-state storage contract and its helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from little_loops.session_store import connect, ensure_db, lifecycle
from little_loops.session_store import usage_source_state as uss
from little_loops.session_store.backend import connect_readonly
from little_loops.session_store.schema import _KINDLESS_TABLES

_TABLES = (
    "usage_source_state",
    "usage_source_pending",
    "usage_observation_witnesses",
    "usage_observation_dependencies",
    "usage_completion_dependencies",
)
_VERSION = lifecycle._USAGE_DERIVE_VERSION
_ACQ = "enh3745-v1"


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    db = tmp_path / "h.db"
    ensure_db(db)
    c = connect(db)
    yield c
    c.close()


def _scope(source: str = "/a.jsonl", generation: str = "g1", **kw: str | None) -> uss.SourceScope:
    return uss.SourceScope(source, generation, _VERSION, **kw)  # type: ignore[arg-type]


def _acquire(
    conn: sqlite3.Connection, scope: uss.SourceScope, offset: int = 100, expected: int | None = None
) -> int:
    return uss.record_source_acquisition(
        conn,
        scope,
        uss.AcquisitionBoundary(_ACQ, offset, 4),
        uss.AcquisitionWitness(1, 2, offset, 3, "ab"),
        expected_head_revision=expected,
    )


def _complete(
    scope: uss.SourceScope, offset: int = 100, *, raw_id: int = 4
) -> uss.SourceDeriveCompletion:
    return uss.SourceDeriveCompletion(
        status="complete",
        reason=None,
        basis="semantic",
        scope=scope,
        boundary=uss.DerivedBoundary(scope, _ACQ, offset, 4, raw_id, "2026-01-01T00:00:00Z"),
    )


class TestMigration:
    def test_five_tables_exist_empty_and_are_kindless(self, conn: sqlite3.Connection) -> None:
        for table in _TABLES:
            assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
            assert table in _KINDLESS_TABLES
        assert uss.storage_available(conn)

    def test_no_foreign_keys_to_cursors_events_or_usage(self, conn: sqlite3.Connection) -> None:
        for table in _TABLES:
            assert conn.execute(f"PRAGMA foreign_key_list({table})").fetchall() == []

    def test_migration_seeds_nothing_from_legacy_cursors(self, tmp_path: Path) -> None:
        db = tmp_path / "h.db"
        ensure_db(db)
        c = sqlite3.connect(str(db))
        try:
            c.execute(
                "INSERT INTO usage_source_cursors VALUES('/a', 'claude-code', 's', 1, 2, 10, 1, "
                "'t', 5, 3, 'complete', '2026-01-01T00:00:00Z')"
            )
            c.commit()
        finally:
            c.close()
        ensure_db(db)
        c = connect(db)
        try:
            assert all(c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] == 0 for t in _TABLES)
            completion = uss.read_source_derive_completion(c, "/a")
        finally:
            c.close()
        assert (completion.status, completion.basis) == ("unprovable", "none")

    def test_check_constraints_reject_malformed_positions(self, conn: sqlite3.Connection) -> None:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO usage_source_state(source_path, generation_id, derive_version, "
                "revision, status, acquired_offset) VALUES('/a', 'g', 'v', 1, 'pending', -1)"
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO usage_source_state(source_path, generation_id, derive_version, "
                "revision, status) VALUES('/a', 'g', 'v', 1, 'done')"
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO usage_source_state(source_path, generation_id, derive_version, "
                "revision, status, acquired_offset) VALUES('/a', 'g', 'v', 1, 'pending', 'x')"
            )


class TestSourceHeadRevisions:
    def test_first_acquisition_inserts_a_pending_head_and_writes_no_completion(
        self, conn: sqlite3.Connection
    ) -> None:
        scope = _scope(host="claude-code", session_id="s")
        assert _acquire(conn, scope) == 1
        head = uss.read_source_head(conn, "/a.jsonl")
        assert head is not None
        assert (head.status, head.reason, head.acquired_offset) == (
            "pending",
            "not_yet_derived",
            100,
        )
        assert head.successful is None
        completion = uss.read_source_derive_completion(conn, "/a.jsonl")
        assert (completion.status, completion.basis) == ("pending", "none")

    def test_null_expected_revision_never_resets_an_existing_head(
        self, conn: sqlite3.Connection
    ) -> None:
        scope = _scope()
        _acquire(conn, scope)
        with pytest.raises(uss.UsageSourceConflict):
            _acquire(conn, scope, expected=None)
        assert uss.head_revision(conn, scope.source_path) == 1

    def test_stale_expected_revision_writes_nothing(self, conn: sqlite3.Connection) -> None:
        scope = _scope()
        _acquire(conn, scope)
        _acquire(conn, scope, 200, expected=1)
        with pytest.raises(uss.UsageSourceConflict):
            _acquire(conn, scope, 300, expected=1)
        head = uss.read_source_head(conn, scope.source_path)
        assert head is not None and (head.revision, head.acquired_offset) == (2, 200)

    def test_revision_survives_cursor_deletion_and_recreation(
        self, conn: sqlite3.Connection
    ) -> None:
        scope = _scope()
        _acquire(conn, scope)
        _acquire(conn, scope, 120, expected=1)
        conn.execute("DELETE FROM usage_source_cursors")
        assert uss.head_revision(conn, scope.source_path) == 2  # tombstone, never reset
        with pytest.raises(uss.UsageSourceConflict):
            _acquire(conn, scope, expected=None)

    def test_acquisition_ahead_of_success_downgrades_complete(
        self, conn: sqlite3.Connection
    ) -> None:
        scope = _scope()
        rev = _acquire(conn, scope)
        rev = uss.publish_source_completion(conn, _complete(scope), (), expected_head_revision=rev)
        assert uss.read_source_derive_completion(conn, scope.source_path).basis == "semantic"
        rev = _acquire(conn, scope, 150, expected=rev)
        head = uss.read_source_head(conn, scope.source_path)
        assert head is not None and (head.status, head.reason) == ("pending", "acquisition_ahead")
        assert head.successful is not None and head.successful.offset == 100  # historical kept

    def test_generation_change_does_not_certify_or_clear_older_obligations(
        self, conn: sqlite3.Connection
    ) -> None:
        old = _scope(generation="g1")
        rev = _acquire(conn, old)
        rev = uss.record_source_pending(
            conn,
            uss.SourcePending(old, "derive_gap", "held_source_skipped"),
            expected_head_revision=rev,
        )
        new = _scope(generation="g2")
        rev = _acquire(conn, new, expected=rev)
        head = uss.read_source_head(conn, old.source_path)
        assert head is not None and head.scope.generation_id == "g2"
        assert (head.status, head.reason) == ("pending", "scope_changed")
        assert len(uss.pending_obligations(conn, old.source_path)) == 1

    def test_older_success_keeps_its_own_scope_when_scope_changes(
        self, conn: sqlite3.Connection
    ) -> None:
        old = _scope(generation="g1", host="claude-code", session_id="s1")
        rev = _acquire(conn, old)
        rev = uss.publish_source_completion(conn, _complete(old), (), expected_head_revision=rev)
        _acquire(conn, _scope(generation="g2", host="claude-code", session_id="s2"), expected=rev)
        head = uss.read_source_head(conn, old.source_path)
        assert head is not None and head.successful is not None
        assert head.successful.scope.generation_id == "g1"
        assert head.successful.scope.session_id == "s1"


class TestPendingObligations:
    def test_first_failure_uses_absent_head_sentinel_and_cas(
        self, conn: sqlite3.Connection
    ) -> None:
        pending = uss.SourcePending(
            _scope(), "acquisition_failure", "decode_failure", first_line_no=3, usage_pending=True
        )
        # A concurrent raw-only acquisition creates the head first.
        _acquire(conn, _scope())
        with pytest.raises(uss.UsageSourceConflict):
            uss.record_source_pending(conn, pending, expected_head_revision=None)
        assert conn.execute("SELECT COUNT(*) FROM usage_source_pending").fetchone()[0] == 0

    def test_no_cursor_failure_creates_unprovable_head(self, conn: sqlite3.Connection) -> None:
        pending = uss.SourcePending(
            _scope(),
            "acquisition_failure",
            "sanitization_refused",
            refusal_code="invalid_payload",
            first_line_no=2,
        )
        assert uss.record_source_pending(conn, pending, expected_head_revision=None) == 1
        assert conn.execute("SELECT COUNT(*) FROM usage_source_cursors").fetchone()[0] == 0
        completion = uss.read_source_derive_completion(conn, "/a.jsonl")
        assert (completion.status, completion.reason) == ("unprovable", "sanitization_refused")
        assert completion.outstanding == "usage"

    def test_merge_keeps_obligation_id_bounds_and_component_union(
        self, conn: sqlite3.Connection
    ) -> None:
        scope = _scope()
        rev = _acquire(conn, scope)
        a = uss.SourcePending(
            scope,
            "derive_gap",
            "held_source_skipped",
            "bounded",
            first_raw_id=5,
            last_raw_id=5,
            first_line_no=5,
            last_line_no=5,
        )
        rev = uss.record_source_pending(conn, a, expected_head_revision=rev)
        b = uss.SourcePending(
            scope,
            "derive_gap",
            "held_source_skipped",
            "bounded",
            first_raw_id=20,
            last_raw_id=22,
            first_line_no=20,
            last_line_no=22,
            raw_cache_pending=True,
            usage_pending=False,
        )
        rev = uss.record_source_pending(conn, b, expected_head_revision=rev)
        (ob,) = uss.pending_obligations(conn, scope.source_path)
        assert (ob.first_raw_id, ob.last_raw_id) == (5, 22)
        assert (ob.first_line_no, ob.last_line_no) == (5, 22)
        assert ob.usage_pending and ob.raw_cache_pending  # union
        row = conn.execute("SELECT revision FROM usage_source_pending").fetchone()
        assert row[0] == 2  # obligation revision tracks its own merges

    def test_whole_source_dominates_and_bounded_needs_a_proved_pair(
        self, conn: sqlite3.Connection
    ) -> None:
        scope = _scope()
        rev = _acquire(conn, scope)
        with pytest.raises(uss.UsageSourceInvalid):
            uss.record_source_pending(
                conn,
                uss.SourcePending(
                    scope, "derive_gap", "held_source_skipped", "bounded", first_raw_id=3
                ),
                expected_head_revision=rev,
            )
        rev = uss.record_source_pending(
            conn,
            uss.SourcePending(
                scope, "derive_gap", "held_source_skipped", "bounded", first_raw_id=3, last_raw_id=4
            ),
            expected_head_revision=rev,
        )
        uss.record_source_pending(
            conn,
            uss.SourcePending(scope, "derive_gap", "held_source_skipped", "whole_source"),
            expected_head_revision=rev,
        )
        (ob,) = uss.pending_obligations(conn, scope.source_path)
        assert ob.range_kind == "whole_source"

    def test_multiple_rejection_classes_coexist(self, conn: sqlite3.Connection) -> None:
        scope = _scope()
        rev = _acquire(conn, scope)
        for kind, reason in (
            ("acquisition_failure", "json_failure"),
            ("acquisition_failure", "decode_failure"),
            ("partial_tail", "partial_tail"),
        ):
            rev = uss.record_source_pending(
                conn, uss.SourcePending(scope, kind, reason), expected_head_revision=rev
            )
        assert len(uss.pending_obligations(conn, scope.source_path)) == 3

    def test_unknown_reason_or_kind_is_rejected(self, conn: sqlite3.Connection) -> None:
        for bad in (
            uss.SourcePending(_scope(), "derive_gap", "free-text with bytes \x00"),
            uss.SourcePending(_scope(), "bogus", "derive_pending"),
            uss.SourcePending(_scope(), "derive_gap", "derive_pending", refusal_code="payload"),
            uss.SourcePending(_scope(), "derive_gap", "derive_pending", usage_pending=False),
        ):
            with pytest.raises(uss.UsageSourceInvalid):
                uss.record_source_pending(conn, bad, expected_head_revision=None)

    def test_completion_refused_while_usage_obligation_remains(
        self, conn: sqlite3.Connection
    ) -> None:
        scope = _scope()
        rev = _acquire(conn, scope)
        rev = uss.record_source_pending(
            conn,
            uss.SourcePending(scope, "derive_gap", "held_source_skipped"),
            expected_head_revision=rev,
        )
        with pytest.raises(uss.UsageSourceConflict):
            uss.publish_source_completion(conn, _complete(scope), (), expected_head_revision=rev)

    def test_cache_only_obligation_does_not_block_completion_but_is_reported(
        self, conn: sqlite3.Connection
    ) -> None:
        scope = _scope()
        rev = _acquire(conn, scope)
        rev = uss.record_source_pending(
            conn,
            uss.SourcePending(
                scope, "refresh", "parser_refresh", raw_cache_pending=True, usage_pending=False
            ),
            expected_head_revision=rev,
        )
        rev = uss.publish_source_completion(conn, _complete(scope), (), expected_head_revision=rev)
        completion = uss.read_source_derive_completion(conn, scope.source_path)
        assert (completion.status, completion.outstanding) == ("complete", "raw_cache")


class TestAcknowledge:
    def _merged(self, conn: sqlite3.Connection) -> tuple[uss.SourceScope, int, str]:
        scope = _scope()
        rev = _acquire(conn, scope)
        for line in (5, 20):
            rev = uss.record_source_pending(
                conn,
                uss.SourcePending(
                    scope,
                    "derive_gap",
                    "held_source_skipped",
                    "bounded",
                    first_raw_id=line,
                    last_raw_id=line,
                    first_line_no=line,
                    last_line_no=line,
                ),
                expected_head_revision=rev,
            )
        (ob,) = uss.pending_obligations(conn, scope.source_path)
        assert ob.obligation_id is not None
        return scope, rev, ob.obligation_id

    def _ob_revision(self, conn: sqlite3.Connection, oid: str) -> int:
        return conn.execute(
            "SELECT revision FROM usage_source_pending WHERE obligation_id = ?", (oid,)
        ).fetchone()[0]

    def test_partial_recovery_through_ten_clears_nothing(self, conn: sqlite3.Connection) -> None:
        scope, rev, oid = self._merged(conn)
        consumed = uss.ConsumedRange(scope, 1, 10, 1, 10)
        assert not uss.acknowledge_source_pending(
            conn,
            oid,
            consumed,
            expected_head_revision=rev,
            expected_obligation_revision=self._ob_revision(conn, oid),
            components=frozenset({"usage"}),
        )
        assert uss.head_revision(conn, scope.source_path) == rev
        assert len(uss.pending_obligations(conn, scope.source_path)) == 1

    def test_full_cover_clears_components_and_deletes_when_both_clear(
        self, conn: sqlite3.Connection
    ) -> None:
        scope = _scope()
        rev = _acquire(conn, scope)
        rev = uss.record_source_pending(
            conn,
            uss.SourcePending(
                scope,
                "refresh",
                "parser_refresh",
                "bounded",
                first_raw_id=2,
                last_raw_id=8,
                raw_cache_pending=True,
                usage_pending=True,
            ),
            expected_head_revision=rev,
        )
        (ob,) = uss.pending_obligations(conn, scope.source_path)
        oid = ob.obligation_id
        assert oid is not None
        cover = uss.ConsumedRange(scope, 1, 9)
        assert uss.acknowledge_source_pending(
            conn,
            oid,
            cover,
            expected_head_revision=rev,
            expected_obligation_revision=self._ob_revision(conn, oid),
            components=frozenset({"usage"}),
        )
        (ob,) = uss.pending_obligations(conn, scope.source_path)
        assert (ob.usage_pending, ob.raw_cache_pending) == (False, True)  # cache kept
        rev = uss.head_revision(conn, scope.source_path) or 0
        assert uss.acknowledge_source_pending(
            conn,
            oid,
            cover,
            expected_head_revision=rev,
            expected_obligation_revision=self._ob_revision(conn, oid),
            components=frozenset({"raw_cache"}),
        )
        assert uss.pending_obligations(conn, scope.source_path) == ()

    def test_stale_head_or_obligation_revision_clears_nothing(
        self, conn: sqlite3.Connection
    ) -> None:
        scope, rev, oid = self._merged(conn)
        full = uss.ConsumedRange(scope, 1, 99, 1, 99)
        ob_rev = self._ob_revision(conn, oid)
        assert not uss.acknowledge_source_pending(
            conn,
            oid,
            full,
            expected_head_revision=rev - 1,
            expected_obligation_revision=ob_rev,
            components=frozenset({"usage"}),
        )
        assert not uss.acknowledge_source_pending(
            conn,
            oid,
            full,
            expected_head_revision=rev,
            expected_obligation_revision=ob_rev - 1,
            components=frozenset({"usage"}),
        )
        assert len(uss.pending_obligations(conn, scope.source_path)) == 1

    def test_whole_source_needs_full_scope_proof_not_a_numeric_bound(
        self, conn: sqlite3.Connection
    ) -> None:
        scope = _scope()
        rev = _acquire(conn, scope)
        rev = uss.record_source_pending(
            conn,
            uss.SourcePending(scope, "refresh", "parser_refresh"),
            expected_head_revision=rev,
        )
        (ob,) = uss.pending_obligations(conn, scope.source_path)
        oid = ob.obligation_id
        assert oid is not None
        ob_rev = self._ob_revision(conn, oid)
        assert not uss.acknowledge_source_pending(
            conn,
            oid,
            uss.ConsumedRange(scope, 1, 10**9, 1, 10**9, 0, 10**9),
            expected_head_revision=rev,
            expected_obligation_revision=ob_rev,
            components=frozenset({"usage"}),
        )
        assert uss.acknowledge_source_pending(
            conn,
            oid,
            uss.ConsumedRange(scope, full_scope=True),
            expected_head_revision=rev,
            expected_obligation_revision=ob_rev,
            components=frozenset({"usage"}),
        )

    def test_older_generation_work_cannot_be_acknowledged_by_the_current_generation(
        self, conn: sqlite3.Connection
    ) -> None:
        scope, rev, oid = self._merged(conn)
        rev = _acquire(conn, _scope(generation="g2"), expected=rev)
        current = uss.ConsumedRange(_scope(generation="g2"), full_scope=True)
        assert not uss.acknowledge_source_pending(
            conn,
            oid,
            current,
            expected_head_revision=rev,
            expected_obligation_revision=self._ob_revision(conn, oid),
            components=frozenset({"usage"}),
        )

    def test_unknown_component_is_rejected(self, conn: sqlite3.Connection) -> None:
        scope, rev, oid = self._merged(conn)
        with pytest.raises(uss.UsageSourceInvalid):
            uss.acknowledge_source_pending(
                conn,
                oid,
                uss.ConsumedRange(scope, full_scope=True),
                expected_head_revision=rev,
                expected_obligation_revision=1,
                components=frozenset({"search"}),
            )


class TestCompletionPublication:
    def test_requires_zero_origin_acquisition_coverage(self, conn: sqlite3.Connection) -> None:
        scope = _scope()
        rev = _acquire(conn, scope, 100)
        with pytest.raises(uss.UsageSourceConflict):  # boundary beyond acquired coverage
            uss.publish_source_completion(
                conn, _complete(scope, 150), (), expected_head_revision=rev
            )
        # No acquisition at all (failure-only head) cannot complete.
        other = _scope("/b.jsonl")
        r2 = uss.record_source_pending(
            conn,
            uss.SourcePending(
                other,
                "acquisition_failure",
                "decode_failure",
                usage_pending=False,
                raw_cache_pending=True,
            ),
            expected_head_revision=None,
        )
        with pytest.raises(uss.UsageSourceConflict):
            uss.publish_source_completion(conn, _complete(other), (), expected_head_revision=r2)

    def test_acquisition_version_mismatch_is_unprovable(self, conn: sqlite3.Connection) -> None:
        scope = _scope()
        rev = _acquire(conn, scope)
        conn.execute("UPDATE usage_source_state SET acquisition_version = 'old'")
        with pytest.raises(uss.UsageSourceConflict):
            uss.publish_source_completion(conn, _complete(scope), (), expected_head_revision=rev)

    def test_publish_replaces_the_bounded_dependency_set(self, conn: sqlite3.Connection) -> None:
        scope = _scope()
        rev = _acquire(conn, scope)
        deps = (
            uss.CompletionDependency("d1", "observation", usage_event_id=7),
            uss.CompletionDependency(
                "d2",
                "context",
                dependency_source_path="/other",
                dependency_generation_id="g9",
                dependency_derive_version=_VERSION,
                line_no=3,
                raw_event_id=11,
            ),
        )
        rev = uss.publish_source_completion(
            conn, _complete(scope), deps, expected_head_revision=rev
        )
        assert conn.execute("SELECT COUNT(*) FROM usage_completion_dependencies").fetchone()[0] == 2
        rev = _acquire(conn, scope, 100, expected=rev)
        rev = uss.publish_source_completion(
            conn, _complete(scope), deps[:1], expected_head_revision=rev
        )
        assert conn.execute("SELECT COUNT(*) FROM usage_completion_dependencies").fetchone()[0] == 1

    def test_stale_revision_publishes_nothing(self, conn: sqlite3.Connection) -> None:
        scope = _scope()
        rev = _acquire(conn, scope)
        _acquire(conn, scope, 100, expected=rev)
        with pytest.raises(uss.UsageSourceConflict):
            uss.publish_source_completion(
                conn,
                _complete(scope),
                (uss.CompletionDependency("d", "observation", usage_event_id=1),),
                expected_head_revision=rev,
            )
        assert conn.execute("SELECT COUNT(*) FROM usage_completion_dependencies").fetchone()[0] == 0

    def test_reader_requires_current_derive_version(
        self, conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        scope = _scope()
        rev = _acquire(conn, scope)
        uss.publish_source_completion(conn, _complete(scope), (), expected_head_revision=rev)
        assert uss.read_source_derive_completion(conn, scope.source_path).basis == "semantic"
        monkeypatch.setattr(lifecycle, "_USAGE_DERIVE_VERSION", "newer")
        completion = uss.read_source_derive_completion(conn, scope.source_path)
        assert (completion.status, completion.basis, completion.reason) == (
            "unprovable",
            "none",
            "version_changed",
        )

    def test_publication_rolls_back_with_its_owner(self, tmp_path: Path) -> None:
        db = tmp_path / "h.db"
        ensure_db(db)
        c = connect(db)
        try:
            c.execute("BEGIN IMMEDIATE")
            scope = _scope()
            rev = _acquire(c, scope)
            uss.publish_source_completion(
                c,
                _complete(scope),
                (uss.CompletionDependency("d", "observation", usage_event_id=1),),
                expected_head_revision=rev,
            )
            c.rollback()
            assert all(c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] == 0 for t in _TABLES)
        finally:
            c.close()


class TestWitnesses:
    def test_legacy_or_missing_witness_reads_as_explicit_unavailable(
        self, conn: sqlite3.Connection
    ) -> None:
        w = uss.read_observation_witness(conn, 42)
        assert (w.value_status, w.qualification_status) == ("unavailable", "unavailable")
        assert w.supplier_source_path is None and w.qualification_dependencies == ()

    def test_supplier_and_frontier_round_trip_and_replace_atomically(
        self, conn: sqlite3.Connection
    ) -> None:
        deps = (
            uss.QualificationDependency("model", "/a", "g1", _VERSION, 3, "codex", "s", 1, 9),
            uss.QualificationDependency("closure", "/a", "g1", _VERSION, 5),
        )
        uss.write_observation_witness(
            conn,
            uss.ObservationWitness(
                7, "known", "known", "/a", "codex", "s", "g1", _VERSION, 3, 1, 9, deps
            ),
        )
        got = uss.read_observation_witness(conn, 7)
        assert got.qualification_dependencies == tuple(
            sorted(deps, key=lambda d: (d.role, d.line_no))
        )
        assert got.supplier_line_no == 3
        uss.write_observation_witness(
            conn,
            uss.ObservationWitness(7, "known", "not_consumed", "/a", None, None, "g1", _VERSION),
        )
        got = uss.read_observation_witness(conn, 7)
        assert got.qualification_dependencies == ()
        assert got.qualification_status == "not_consumed"

    def test_unavailable_evidence_cannot_be_an_empty_proved_frontier(
        self, conn: sqlite3.Connection
    ) -> None:
        with pytest.raises(uss.UsageSourceInvalid):
            uss.write_observation_witness(
                conn,
                uss.ObservationWitness(
                    7,
                    "known",
                    "unavailable",
                    qualification_dependencies=(
                        uss.QualificationDependency("model", "/a", "g1", _VERSION, 3),
                    ),
                ),
            )

    def test_witness_write_rolls_back_together(self, tmp_path: Path) -> None:
        db = tmp_path / "h.db"
        ensure_db(db)
        c = connect(db)
        try:
            c.execute("BEGIN IMMEDIATE")
            uss.write_observation_witness(
                c,
                uss.ObservationWitness(
                    7,
                    "known",
                    "known",
                    "/a",
                    None,
                    None,
                    "g1",
                    _VERSION,
                    3,
                    qualification_dependencies=(
                        uss.QualificationDependency("model", "/a", "g1", _VERSION, 3),
                    ),
                ),
            )
            c.rollback()
            assert c.execute("SELECT COUNT(*) FROM usage_observation_witnesses").fetchone()[0] == 0
            assert (
                c.execute("SELECT COUNT(*) FROM usage_observation_dependencies").fetchone()[0] == 0
            )
        finally:
            c.close()


class TestInvalidation:
    def _tracked(self, conn: sqlite3.Connection, source: str, deps: tuple = ()) -> int:
        scope = _scope(source)
        rev = _acquire(conn, scope)
        return uss.publish_source_completion(
            conn, _complete(scope), deps, expected_head_revision=rev
        )

    def test_dependents_become_pending_and_history_is_kept(self, conn: sqlite3.Connection) -> None:
        self._tracked(
            conn, "/a.jsonl", (uss.CompletionDependency("d1", "observation", usage_event_id=7),)
        )
        self._tracked(conn, "/b.jsonl")
        uss.write_observation_witness(
            conn,
            uss.ObservationWitness(7, "known", "not_consumed", "/c", None, None, "g", _VERSION),
        )
        uss.invalidate_usage_dependencies(conn, (7,), (), reason="codex_catchup")
        a = uss.read_source_derive_completion(conn, "/a.jsonl")
        b = uss.read_source_derive_completion(conn, "/b.jsonl")
        assert (a.status, a.basis, a.outstanding) == ("pending", "none", "usage")
        assert b.basis == "semantic"  # unrelated source untouched
        assert a.boundary is not None and a.boundary.offset == 100  # historical boundary kept
        assert uss.read_observation_witness(conn, 7).value_status == "unavailable"
        assert conn.execute("SELECT COUNT(*) FROM usage_completion_dependencies").fetchone()[0] == 0

    def test_explicit_scopes_and_cross_source_context_dependents(
        self, conn: sqlite3.Connection
    ) -> None:
        self._tracked(conn, "/a.jsonl")
        self._tracked(
            conn,
            "/copy.jsonl",
            (
                uss.CompletionDependency(
                    "c1",
                    "context",
                    dependency_source_path="/a.jsonl",
                    dependency_generation_id="g1",
                    dependency_derive_version=_VERSION,
                    line_no=2,
                ),
            ),
        )
        uss.invalidate_usage_dependencies(conn, (), (_scope("/a.jsonl"),), reason="parser_refresh")
        for source in ("/a.jsonl", "/copy.jsonl"):
            completion = uss.read_source_derive_completion(conn, source)
            assert (completion.status, completion.outstanding) == ("pending", "both")

    def test_untracked_source_is_left_alone(self, conn: sqlite3.Connection) -> None:
        uss.invalidate_usage_dependencies(conn, (), (_scope("/nope"),), reason="rebuild")
        assert conn.execute("SELECT COUNT(*) FROM usage_source_state").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM usage_source_pending").fetchone()[0] == 0

    def test_failure_between_invalidation_and_replay_restores_everything(
        self, tmp_path: Path
    ) -> None:
        db = tmp_path / "h.db"
        ensure_db(db)
        c = connect(db)
        try:
            c.execute("BEGIN IMMEDIATE")
            self._tracked(c, "/a.jsonl")
            c.commit()
            c.execute("BEGIN IMMEDIATE")
            uss.invalidate_usage_dependencies(c, (), (_scope("/a.jsonl"),), reason="rebuild")
            c.rollback()
            assert uss.read_source_derive_completion(c, "/a.jsonl").basis == "semantic"
            assert c.execute("SELECT COUNT(*) FROM usage_source_pending").fetchone()[0] == 0
        finally:
            c.close()

    def test_unknown_reason_is_rejected(self, conn: sqlite3.Connection) -> None:
        with pytest.raises(uss.UsageSourceInvalid):
            uss.invalidate_usage_dependencies(conn, (), (), reason="whatever")


class TestReadersOnOtherMembers:
    def test_attached_members_keep_independent_state(self, tmp_path: Path) -> None:
        a, b = tmp_path / "a.db", tmp_path / "b.db"
        for path in (a, b):
            ensure_db(path)
        ca = connect(a)
        try:
            scope = _scope("/same.jsonl")
            rev = _acquire(ca, scope)
            uss.publish_source_completion(ca, _complete(scope), (), expected_head_revision=rev)
            ca.commit()
            cb = connect(b)
            try:
                rb = _acquire(cb, _scope("/same.jsonl"))
                uss.record_source_pending(
                    cb,
                    uss.SourcePending(_scope("/same.jsonl"), "derive_gap", "held_source_skipped"),
                    expected_head_revision=rb,
                )
                cb.commit()
            finally:
                cb.close()
            ca.execute("ATTACH DATABASE ? AS other", (str(b),))
            assert uss.read_source_derive_completion(ca, "/same.jsonl").basis == "semantic"
            other = uss.read_source_derive_completion(ca, "/same.jsonl", schema="other")
            assert (other.status, other.basis) == ("pending", "none")
        finally:
            ca.close()

    @pytest.mark.parametrize(
        "alias", ["nope", "main; DROP TABLE meta", "x" * 80, "", "1bad", 'a"b']
    )
    def test_malicious_or_unknown_alias_is_unavailable_not_main(
        self, conn: sqlite3.Connection, alias: str
    ) -> None:
        scope = _scope()
        rev = _acquire(conn, scope)
        uss.publish_source_completion(conn, _complete(scope), (), expected_head_revision=rev)
        got = uss.read_source_derive_completion(conn, scope.source_path, schema=alias)
        assert (got.status, got.reason, got.basis) == ("unprovable", "storage_unavailable", "none")
        assert uss.read_observation_witness(conn, 1, schema=alias).value_status == "unavailable"
        assert conn.execute("SELECT COUNT(*) FROM meta").fetchone()[0] > 0

    def test_pre_migration_member_is_unavailable_without_migration_or_writes(
        self, tmp_path: Path
    ) -> None:
        old = tmp_path / "old.db"
        ensure_db(old)
        raw = sqlite3.connect(str(old))
        for table in _TABLES:
            raw.execute(f"DROP TABLE {table}")
        raw.commit()
        raw.close()
        ro = connect_readonly(old)
        try:
            ro.execute("BEGIN")
            got = uss.read_source_derive_completion(ro, "/a")
            assert (got.status, got.reason) == ("unprovable", "storage_unavailable")
            assert uss.read_observation_witness(ro, 1).value_status == "unavailable"
            assert not uss.storage_available(ro)
            ro.rollback()
        finally:
            ro.close()
        raw = sqlite3.connect(str(old))
        try:
            names = {r[0] for r in raw.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            raw.close()
        assert not names & set(_TABLES)

    def test_reader_on_query_only_snapshot_never_writes(self, tmp_path: Path) -> None:
        db = tmp_path / "h.db"
        ensure_db(db)
        c = connect(db)
        scope = _scope()
        rev = _acquire(c, scope)
        uss.publish_source_completion(c, _complete(scope), (), expected_head_revision=rev)
        c.commit()
        c.close()
        ro = connect_readonly(db)
        try:
            ro.execute("BEGIN")
            assert uss.read_source_derive_completion(ro, scope.source_path).basis == "semantic"
            assert uss.read_source_derive_completion(ro, "/other").reason == "untracked"
            ro.rollback()
        finally:
            ro.close()


def test_prior_semantic_success_gate_ignores_failure_only_heads(conn: sqlite3.Connection) -> None:
    uss.record_source_pending(
        conn,
        uss.SourcePending(_scope(), "acquisition_failure", "decode_failure"),
        expected_head_revision=None,
    )
    assert not uss.has_prior_semantic_success(conn)
    scope = _scope("/ok.jsonl")
    rev = _acquire(conn, scope)
    uss.publish_source_completion(conn, _complete(scope), (), expected_head_revision=rev)
    assert uss.has_prior_semantic_success(conn)


class TestAttachedProofScope:
    """The shared ENH-3744 collector selects exactly one validated member."""

    def _members(self, tmp_path: Path) -> tuple[Path, Path, Path]:
        from little_loops.session_store import backfill_raw_events, refresh_usage_source

        tmp = tmp_path.resolve()
        source = tmp / "session.jsonl"
        source.write_bytes(
            (Path(__file__).parent / "fixtures/claude/transcript-v2.1.284.jsonl").read_bytes()
        )
        full, raw_only = tmp / "full.db", tmp / "raw.db"
        refresh_usage_source(full, source)  # observations derived
        backfill_raw_events(raw_only, jsonl_files=[source], host="claude-code")  # none derived
        return full, raw_only, source

    def test_colliding_paths_and_raw_ids_keep_independent_proof(self, tmp_path: Path) -> None:
        from collections import Counter

        from little_loops.session_store.usage_proof_scope import inspect_retained_source

        full, raw_only, source = self._members(tmp_path)
        conn = connect(full)
        try:
            conn.execute("ATTACH DATABASE ? AS other", (str(raw_only),))
            main = Counter(p.correspondence for p in inspect_retained_source(conn, str(source)))
            other = Counter(
                p.correspondence for p in inspect_retained_source(conn, str(source), schema="other")
            )
        finally:
            conn.close()
        assert main["represented"] >= 1 and main["missing"] == 0
        assert other["missing"] >= 1 and other["represented"] == 0

    @pytest.mark.parametrize("alias", ["nope", "main; DROP TABLE meta", "", "1x", 'a"b'])
    def test_unknown_or_malicious_alias_never_falls_through_to_main(
        self, tmp_path: Path, alias: str
    ) -> None:
        from little_loops.session_store.usage_proof_scope import (
            UsageProofUnavailable,
            collect_usage_proof_scope,
        )

        full, _, source = self._members(tmp_path)
        conn = connect(full)
        try:
            with pytest.raises(UsageProofUnavailable):
                collect_usage_proof_scope(conn, str(source), schema=alias)
        finally:
            conn.close()

    def test_old_schema_member_without_proof_tables_is_unavailable(self, tmp_path: Path) -> None:
        from little_loops.session_store.usage_proof_scope import (
            UsageProofUnavailable,
            collect_usage_proof_scope,
        )

        full, _, source = self._members(tmp_path)
        old = tmp_path / "old.db"
        raw = sqlite3.connect(str(old))
        raw.execute("CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT)")
        raw.commit()
        raw.close()
        conn = connect(full)
        try:
            conn.execute("ATTACH DATABASE ? AS legacy", (str(old),))
            with pytest.raises(UsageProofUnavailable):
                collect_usage_proof_scope(conn, str(source), schema="legacy")
        finally:
            conn.close()
