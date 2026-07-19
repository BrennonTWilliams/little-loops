"""Tests for little_loops.queue_store - the persisted ll-queue entry store (FEAT-2682)."""

from __future__ import annotations

import itertools
import re
import sqlite3
from pathlib import Path

import pytest

from little_loops.queue_store import (
    PRIORITY_TIERS,
    SCHEMA_VERSION,
    AmbiguousEntryIdError,
    add_entry,
    connect,
    ensure_db,
    get_entry,
    list_entries,
    remove_entry,
    resolve_entry,
    update_entry_result,
)
from little_loops.runner_spec import ActionSpec, RunnerType

_TMP_COUNTER = itertools.count()


@pytest.fixture(scope="module")
def _module_tmp_parent(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One temp parent per module instead of one top-level dir per test."""
    return tmp_path_factory.mktemp("queue_store")


@pytest.fixture
def tmp_path(_module_tmp_parent: Path, request: pytest.FixtureRequest) -> Path:
    """Override built-in tmp_path: unique fresh subdir of the module parent."""
    name = re.sub(r"\W", "_", request.node.name)[:30]
    path = _module_tmp_parent / f"{name}_{next(_TMP_COUNTER)}"
    path.mkdir()
    return path


def _spec(name: str = "audit-docs", runner: RunnerType = RunnerType.SKILL) -> ActionSpec:
    return ActionSpec(name=name, runner=runner, target=name)


class TestEnsureDb:
    def test_creates_database_file(self, tmp_path: Path) -> None:
        db = tmp_path / "nested" / "queue.db"
        result = ensure_db(db)
        assert result == db
        assert db.exists()

    def test_idempotent(self, tmp_path: Path) -> None:
        db = tmp_path / "queue.db"
        ensure_db(db)
        ensure_db(db)  # must not raise on re-run

        conn = sqlite3.connect(str(db))
        row = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
        conn.close()
        assert int(row[0]) == SCHEMA_VERSION


class TestAddEntry:
    def test_persists_entry(self, tmp_path: Path) -> None:
        db = tmp_path / "queue.db"
        entry = add_entry(_spec(), "P2", db_path=db)

        assert entry.priority == "P2"
        assert entry.status == "pending"
        assert entry.result is None
        assert entry.action.name == "audit-docs"

        fetched = get_entry(entry.id, db)
        assert fetched is not None
        assert fetched.id == entry.id
        assert fetched.action.runner == RunnerType.SKILL

    def test_default_priority(self, tmp_path: Path) -> None:
        db = tmp_path / "queue.db"
        entry = add_entry(_spec(), db_path=db)
        assert entry.priority == "P3"

    def test_invalid_priority_raises(self, tmp_path: Path) -> None:
        db = tmp_path / "queue.db"
        with pytest.raises(ValueError):
            add_entry(_spec(), "P9", db_path=db)

    def test_all_three_action_spec_kinds_persist(self, tmp_path: Path) -> None:
        db = tmp_path / "queue.db"
        loop_entry = add_entry(
            ActionSpec(name="my-loop", runner=RunnerType.LOOP, target="my-loop"), db_path=db
        )
        skill_entry = add_entry(
            ActionSpec(name="audit-docs", runner=RunnerType.SKILL, target="audit-docs"),
            db_path=db,
        )
        cmd_entry = add_entry(
            ActionSpec(name="pytest scripts/tests/", runner=RunnerType.CMD, target="pytest"),
            db_path=db,
        )

        assert get_entry(loop_entry.id, db).action.runner == RunnerType.LOOP
        assert get_entry(skill_entry.id, db).action.runner == RunnerType.SKILL
        assert get_entry(cmd_entry.id, db).action.runner == RunnerType.CMD


class TestListEntries:
    def test_empty_queue(self, tmp_path: Path) -> None:
        db = tmp_path / "queue.db"
        ensure_db(db)
        assert list_entries(db) == []

    def test_priority_tier_ordering(self, tmp_path: Path) -> None:
        db = tmp_path / "queue.db"
        p2 = add_entry(_spec("p2-item"), "P2", db_path=db)
        p0 = add_entry(_spec("p0-item"), "P0", db_path=db)
        p5 = add_entry(_spec("p5-item"), "P5", db_path=db)

        ids = [e.id for e in list_entries(db)]
        assert ids == [p0.id, p2.id, p5.id]

    def test_fifo_within_tier(self, tmp_path: Path) -> None:
        """Entries at the same priority tier preserve insertion (FIFO) order."""
        db = tmp_path / "queue.db"
        first = add_entry(_spec("first"), "P3", db_path=db)
        second = add_entry(_spec("second"), "P3", db_path=db)
        third = add_entry(_spec("third"), "P3", db_path=db)

        ids = [e.id for e in list_entries(db)]
        assert ids == [first.id, second.id, third.id]

    def test_priority_tiers_constant_matches_expected_order(self) -> None:
        assert PRIORITY_TIERS == ("P0", "P1", "P2", "P3", "P4", "P5")


class TestGetEntry:
    def test_returns_none_when_missing(self, tmp_path: Path) -> None:
        db = tmp_path / "queue.db"
        ensure_db(db)
        assert get_entry("does-not-exist", db) is None


class TestResolveEntry:
    def test_resolves_exact_id(self, tmp_path: Path) -> None:
        db = tmp_path / "queue.db"
        entry = add_entry(_spec(), db_path=db)
        assert resolve_entry(entry.id, db).id == entry.id

    def test_resolves_prefix(self, tmp_path: Path) -> None:
        db = tmp_path / "queue.db"
        entry = add_entry(_spec(), db_path=db)
        assert resolve_entry(entry.id[:8], db).id == entry.id

    def test_returns_none_for_unknown(self, tmp_path: Path) -> None:
        db = tmp_path / "queue.db"
        ensure_db(db)
        assert resolve_entry("deadbeef", db) is None

    def test_short_prefix_below_8_chars_not_matched(self, tmp_path: Path) -> None:
        db = tmp_path / "queue.db"
        add_entry(_spec(), db_path=db)
        assert resolve_entry("ab", db) is None

    def test_ambiguous_prefix_raises(self, tmp_path: Path) -> None:
        db = tmp_path / "queue.db"
        # Force a collision by adding entries and asserting on a real shared
        # prefix derived from two persisted ids.
        e1 = add_entry(_spec("one"), db_path=db)
        e2 = add_entry(_spec("two"), db_path=db)
        shared = None
        for length in range(8, 33):
            if e1.id[:length] == e2.id[:length]:
                shared = e1.id[:length]
            else:
                break
        if shared is None:
            pytest.skip("no natural id collision to test ambiguity with")
        with pytest.raises(AmbiguousEntryIdError):
            resolve_entry(shared, db)


class TestRemoveEntry:
    def test_removes_existing_entry(self, tmp_path: Path) -> None:
        db = tmp_path / "queue.db"
        entry = add_entry(_spec(), db_path=db)
        assert remove_entry(entry.id, db) is True
        assert get_entry(entry.id, db) is None

    def test_returns_false_for_unknown_id(self, tmp_path: Path) -> None:
        db = tmp_path / "queue.db"
        ensure_db(db)
        assert remove_entry("does-not-exist", db) is False


class TestUpdateEntryResult:
    def test_updates_status_and_result(self, tmp_path: Path) -> None:
        db = tmp_path / "queue.db"
        entry = add_entry(_spec(), db_path=db)
        updated = update_entry_result(entry.id, "done", {"exit_code": 0, "error": None}, db_path=db)
        assert updated is True

        fetched = get_entry(entry.id, db)
        assert fetched.status == "done"
        assert fetched.result == {"exit_code": 0, "error": None}

    def test_returns_false_for_unknown_id(self, tmp_path: Path) -> None:
        db = tmp_path / "queue.db"
        ensure_db(db)
        assert update_entry_result("does-not-exist", "done", None, db_path=db) is False


class TestConnect:
    def test_returns_row_factory_connection(self, tmp_path: Path) -> None:
        db = tmp_path / "queue.db"
        conn = connect(db)
        try:
            assert conn.row_factory is sqlite3.Row
        finally:
            conn.close()
