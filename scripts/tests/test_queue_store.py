"""Tests for little_loops.queue_store - the persisted ll-queue entry store (FEAT-2682)."""

from __future__ import annotations

import itertools
import re
import sqlite3
import threading
from pathlib import Path

import pytest

from little_loops.queue_store import (
    PRIORITY_TIERS,
    QUEUE_BACKOFF_BASE_S,
    QUEUE_BACKOFF_CEILING_S,
    QUEUE_MAX_ATTEMPTS,
    QUEUE_RETRYABLE_REASONS,
    QUEUE_STATUSES,
    QUEUE_TERMINAL_STATUSES,
    SCHEMA_VERSION,
    AmbiguousEntryIdError,
    add_entry,
    cancel_entry,
    claim_entry,
    compute_backoff_s,
    connect,
    dead_letter_entry,
    ensure_db,
    get_entry,
    list_entries,
    remove_entry,
    reset_to_pending,
    resolve_entry,
    revive_entry,
    schedule_retry,
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


class TestDefaultPathResolution:
    """ENH-2927: the default DEFAULT_DB_PATH branch anchors at resolve_ll_dir(), not bare cwd."""

    def test_default_anchors_at_resolved_project_root(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from little_loops.queue_store import DEFAULT_DB_PATH

        project_root = tmp_path / "project"
        (project_root / ".ll").mkdir(parents=True)
        sub = project_root / "sub"
        sub.mkdir()
        monkeypatch.chdir(sub)

        result = ensure_db(DEFAULT_DB_PATH)
        assert result == project_root / ".ll" / "queue.db"
        assert result.exists()
        # No stray .ll/ created at the subdirectory cwd.
        assert not (sub / ".ll").exists()

    def test_default_falls_back_to_cwd_when_no_root_resolves(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from little_loops.queue_store import DEFAULT_DB_PATH

        isolated = tmp_path / "no-project-anywhere"
        isolated.mkdir()
        monkeypatch.chdir(isolated)

        result = ensure_db(DEFAULT_DB_PATH)
        assert result == isolated / DEFAULT_DB_PATH
        assert result.exists()

    def test_explicit_path_overrides_default_resolution(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A deliberate non-default-shaped path is never rerouted through resolve_ll_dir."""
        project_root = tmp_path / "project"
        (project_root / ".ll").mkdir(parents=True)
        monkeypatch.chdir(project_root)

        explicit = tmp_path / "elsewhere" / "custom.db"
        result = ensure_db(explicit)
        assert result == explicit
        assert result.exists()


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

    def test_timeout_none_round_trips_as_json_null(self, tmp_path: Path) -> None:
        """BUG-2928: a LOOP entry's unbounded timeout survives JSON serialize/deserialize."""
        db = tmp_path / "queue.db"
        entry = add_entry(
            ActionSpec(name="my-loop", runner=RunnerType.LOOP, target="my-loop", timeout=None),
            db_path=db,
        )

        fetched = get_entry(entry.id, db)
        assert fetched is not None
        assert fetched.action.timeout is None

    def test_scopes_round_trips(self, tmp_path: Path) -> None:
        """ENH-3234 AC6: a scoped ActionSpec's `scopes` field survives the
        ll-queue persist/fetch round-trip instead of silently vanishing."""
        db = tmp_path / "queue.db"
        entry = add_entry(
            ActionSpec(
                name="x", runner=RunnerType.CMD, target="echo hi", scopes=frozenset({"github"})
            ),
            db_path=db,
        )

        fetched = get_entry(entry.id, db)
        assert fetched is not None
        assert fetched.action.scopes == frozenset({"github"})

    def test_no_scopes_round_trips_as_none(self, tmp_path: Path) -> None:
        """A scopes=None ActionSpec must round-trip to None, not an empty frozenset —
        None means "undeclared, full-inherit"; frozenset() means "declared, deny-all"."""
        db = tmp_path / "queue.db"
        entry = add_entry(_spec(), db_path=db)

        fetched = get_entry(entry.id, db)
        assert fetched is not None
        assert fetched.action.scopes is None

    def test_scoped_skill_entry_rejected(self, tmp_path: Path) -> None:
        """ENH-3403: scopes on SKILL/PROMPT/MCP are never enforced at dispatch,
        so add_entry() must reject the combination rather than persist it."""
        db = tmp_path / "queue.db"
        with pytest.raises(ValueError, match="declares 'scopes' but runner is"):
            add_entry(
                ActionSpec(
                    name="x", runner=RunnerType.SKILL, target="x", scopes=frozenset({"github"})
                ),
                db_path=db,
            )
        assert list_entries(db) == []


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
        claim_entry(entry.id, db_path=db)
        updated = update_entry_result(entry.id, "done", {"exit_code": 0, "error": None}, db_path=db)
        assert updated is True

        fetched = get_entry(entry.id, db)
        assert fetched.status == "done"
        assert fetched.result == {"exit_code": 0, "error": None}

    def test_returns_false_for_unknown_id(self, tmp_path: Path) -> None:
        db = tmp_path / "queue.db"
        ensure_db(db)
        assert update_entry_result("does-not-exist", "done", None, db_path=db) is False

    def test_write_to_non_running_row_returns_false_and_leaves_row_unchanged(
        self, tmp_path: Path
    ) -> None:
        """New status-guarded completion write: a `pending` row is not a valid
        target for a completion write (only `_drain_once` transitions
        running -> terminal); the row must be left untouched on a guard miss."""
        db = tmp_path / "queue.db"
        entry = add_entry(_spec(), db_path=db)  # still pending, never claimed

        updated = update_entry_result(entry.id, "done", {"exit_code": 0}, db_path=db)
        assert updated is False

        fetched = get_entry(entry.id, db)
        assert fetched is not None
        assert fetched.status == "pending"
        assert fetched.result is None


class TestClaimEntry:
    def test_claims_pending_entry(self, tmp_path: Path) -> None:
        db = tmp_path / "queue.db"
        entry = add_entry(_spec(), db_path=db)
        assert claim_entry(entry.id, db_path=db) is True

        fetched = get_entry(entry.id, db)
        assert fetched.status == "running"

    def test_returns_false_for_non_pending_entry(self, tmp_path: Path) -> None:
        db = tmp_path / "queue.db"
        entry = add_entry(_spec(), db_path=db)
        assert claim_entry(entry.id, db_path=db) is True  # pending -> running
        assert claim_entry(entry.id, db_path=db) is False  # already running

        update_entry_result(entry.id, "done", None, db_path=db)
        assert claim_entry(entry.id, db_path=db) is False  # done

    def test_returns_false_for_unknown_id(self, tmp_path: Path) -> None:
        db = tmp_path / "queue.db"
        ensure_db(db)
        assert claim_entry("does-not-exist", db_path=db) is False

    def test_concurrent_claims_exactly_one_winner(self, tmp_path: Path) -> None:
        """Two threads racing claim_entry() on the same pending row: exactly one wins (BUG-2929)."""
        db = tmp_path / "queue.db"
        entry = add_entry(_spec(), db_path=db)

        results: list[bool] = []
        results_lock = threading.Lock()
        barrier = threading.Barrier(2)

        def try_claim() -> None:
            barrier.wait()
            result = claim_entry(entry.id, db_path=db)
            with results_lock:
                results.append(result)

        t1 = threading.Thread(target=try_claim)
        t2 = threading.Thread(target=try_claim)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert sorted(results) == [False, True]
        assert get_entry(entry.id, db).status == "running"

    def test_claim_increments_attempt(self, tmp_path: Path) -> None:
        db = tmp_path / "queue.db"
        entry = add_entry(_spec(), db_path=db)
        assert entry.attempt == 0

        claim_entry(entry.id, db_path=db)
        assert get_entry(entry.id, db).attempt == 1

        # A dead-drainer reclaim (reset_to_pending) followed by a second claim
        # increments again -- attempt survives a dead drainer with no extra
        # bookkeeping.
        reset_to_pending(entry.id, db_path=db)
        claim_entry(entry.id, db_path=db)
        assert get_entry(entry.id, db).attempt == 2

    def test_claim_refuses_row_with_future_next_attempt_at(self, tmp_path: Path) -> None:
        db = tmp_path / "queue.db"
        entry = add_entry(_spec(), db_path=db)
        claim_entry(entry.id, db_path=db)
        schedule_retry(entry.id, "boom", "2999-01-01T00:00:00Z", db_path=db)

        assert claim_entry(entry.id, db_path=db, now="2026-01-01T00:00:00Z") is False
        assert get_entry(entry.id, db).status == "pending"

    def test_claim_accepts_row_whose_next_attempt_at_has_elapsed(self, tmp_path: Path) -> None:
        db = tmp_path / "queue.db"
        entry = add_entry(_spec(), db_path=db)
        claim_entry(entry.id, db_path=db)
        schedule_retry(entry.id, "boom", "2026-01-01T00:00:00Z", db_path=db)

        assert claim_entry(entry.id, db_path=db, now="2026-06-01T00:00:00Z") is True
        assert get_entry(entry.id, db).status == "running"


class TestComputeBackoffS:
    def test_doubling_sequence_with_ceiling(self) -> None:
        assert [compute_backoff_s(n) for n in range(1, 8)] == [5, 10, 20, 40, 80, 160, 300]


class TestConstantsLock:
    """Guards the policy constants against silent drift (ENH-3416 AC)."""

    def test_constants_match_declared_values(self) -> None:
        assert QUEUE_MAX_ATTEMPTS == 5
        assert QUEUE_BACKOFF_BASE_S == 5
        assert QUEUE_BACKOFF_CEILING_S == 300

    def test_max_attempts_greater_than_one(self) -> None:
        assert QUEUE_MAX_ATTEMPTS > 1


class TestStatusVocabulary:
    def test_statuses_and_terminal_subset(self) -> None:
        assert QUEUE_STATUSES == {
            "pending",
            "running",
            "done",
            "failed",
            "dead_letter",
            "cancelled",
        }
        assert QUEUE_TERMINAL_STATUSES == {"done", "failed", "dead_letter", "cancelled"}
        assert QUEUE_TERMINAL_STATUSES.issubset(QUEUE_STATUSES)


class TestRetryableReasonsJoinLock:
    """Guards QUEUE_RETRYABLE_REASONS against drift in classify_failure's reason text."""

    def test_every_retryable_reason_is_actually_produced(self) -> None:
        from little_loops.issue_lifecycle import classify_failure

        produced = {
            classify_failure("429 too many requests", 1)[1],
            classify_failure("connection refused", 1)[1],
            classify_failure("the server had an error", 1)[1],
            classify_failure("", 143, result_seen=True)[1],
        }
        assert QUEUE_RETRYABLE_REASONS.issubset(produced)

    def test_command_timeout_is_not_retryable(self) -> None:
        assert "Command timeout" not in QUEUE_RETRYABLE_REASONS


class TestScheduleRetry:
    def test_returns_running_entry_to_pending_with_next_attempt_at(self, tmp_path: Path) -> None:
        db = tmp_path / "queue.db"
        entry = add_entry(_spec(), db_path=db)
        claim_entry(entry.id, db_path=db)

        assert schedule_retry(entry.id, "429", "2026-01-01T00:00:05Z", db_path=db) is True

        fetched = get_entry(entry.id, db)
        assert fetched is not None
        assert fetched.status == "pending"
        assert fetched.next_attempt_at == "2026-01-01T00:00:05Z"
        assert fetched.result == {"error": "429"}
        assert fetched.claimed_at is None
        assert fetched.owner_pid is None

    def test_guard_miss_on_non_running_row_returns_false(self, tmp_path: Path) -> None:
        db = tmp_path / "queue.db"
        entry = add_entry(_spec(), db_path=db)  # still pending
        assert schedule_retry(entry.id, "429", "2026-01-01T00:00:05Z", db_path=db) is False
        assert get_entry(entry.id, db).status == "pending"


class TestDeadLetterEntry:
    def test_moves_running_entry_to_dead_letter(self, tmp_path: Path) -> None:
        db = tmp_path / "queue.db"
        entry = add_entry(_spec(), db_path=db)
        claim_entry(entry.id, db_path=db)

        assert dead_letter_entry(entry.id, "budget exhausted", db_path=db) is True

        fetched = get_entry(entry.id, db)
        assert fetched is not None
        assert fetched.status == "dead_letter"
        assert fetched.result == {"error": "budget exhausted"}
        assert fetched.claimed_at is None
        assert fetched.owner_pid is None

    def test_guard_miss_on_non_running_row_returns_false(self, tmp_path: Path) -> None:
        db = tmp_path / "queue.db"
        entry = add_entry(_spec(), db_path=db)  # still pending
        assert dead_letter_entry(entry.id, "boom", db_path=db) is False
        assert get_entry(entry.id, db).status == "pending"


class TestCancelEntry:
    def test_cancels_pending_entry(self, tmp_path: Path) -> None:
        db = tmp_path / "queue.db"
        entry = add_entry(_spec(), db_path=db)

        assert cancel_entry(entry.id, "no longer needed", db_path=db) is True

        fetched = get_entry(entry.id, db)
        assert fetched is not None
        assert fetched.status == "cancelled"
        assert fetched.result == {"reason": "no longer needed"}

    def test_cancels_running_entry(self, tmp_path: Path) -> None:
        db = tmp_path / "queue.db"
        entry = add_entry(_spec(), db_path=db)
        claim_entry(entry.id, db_path=db)

        assert cancel_entry(entry.id, "interrupted by operator", db_path=db) is True
        assert get_entry(entry.id, db).status == "cancelled"

    def test_extra_dict_merges_under_reason(self, tmp_path: Path) -> None:
        db = tmp_path / "queue.db"
        entry = add_entry(_spec(), db_path=db)
        claim_entry(entry.id, db_path=db)

        cancel_entry(
            entry.id,
            "interrupted by operator",
            db_path=db,
            extra={"exit_code": 1, "stdout": "partial"},
        )
        fetched = get_entry(entry.id, db)
        assert fetched is not None
        assert fetched.result == {
            "exit_code": 1,
            "stdout": "partial",
            "reason": "interrupted by operator",
        }

    def test_guard_miss_on_terminal_row_returns_false(self, tmp_path: Path) -> None:
        db = tmp_path / "queue.db"
        entry = add_entry(_spec(), db_path=db)
        claim_entry(entry.id, db_path=db)
        update_entry_result(entry.id, "done", {"exit_code": 0}, db_path=db)

        assert cancel_entry(entry.id, "too late", db_path=db) is False
        assert get_entry(entry.id, db).status == "done"


class TestReviveEntry:
    def test_revives_dead_letter_entry_with_fresh_budget(self, tmp_path: Path) -> None:
        db = tmp_path / "queue.db"
        entry = add_entry(_spec(), db_path=db)
        claim_entry(entry.id, db_path=db)
        dead_letter_entry(entry.id, "budget exhausted", db_path=db)

        assert revive_entry(entry.id, db_path=db) is True

        fetched = get_entry(entry.id, db)
        assert fetched is not None
        assert fetched.status == "pending"
        assert fetched.attempt == 0
        assert fetched.next_attempt_at is None
        assert fetched.result == {"previous": {"error": "budget exhausted"}}

    def test_revives_failed_and_cancelled_entries(self, tmp_path: Path) -> None:
        db = tmp_path / "queue.db"
        failed = add_entry(_spec("f"), db_path=db)
        claim_entry(failed.id, db_path=db)
        update_entry_result(failed.id, "failed", {"error": "boom"}, db_path=db)
        assert revive_entry(failed.id, db_path=db) is True
        assert get_entry(failed.id, db).status == "pending"

        cancelled = add_entry(_spec("c"), db_path=db)
        cancel_entry(cancelled.id, "stop", db_path=db)
        assert revive_entry(cancelled.id, db_path=db) is True
        assert get_entry(cancelled.id, db).status == "pending"

    def test_revive_with_no_prior_result_leaves_result_null(self, tmp_path: Path) -> None:
        db = tmp_path / "queue.db"
        entry = add_entry(_spec(), db_path=db)
        cancel_entry(entry.id, "stop", db_path=db)
        update_entry_result(entry.id, "cancelled", None, db_path=db)
        # cancel_entry always sets a reason, so force a null-result terminal
        # row directly to cover the "no prior result" branch.
        conn = connect(db)
        try:
            conn.execute("UPDATE queue_entries SET result = NULL WHERE id = ?", (entry.id,))
            conn.commit()
        finally:
            conn.close()

        assert revive_entry(entry.id, db_path=db) is True
        assert get_entry(entry.id, db).result is None

    def test_returns_false_for_unknown_id(self, tmp_path: Path) -> None:
        db = tmp_path / "queue.db"
        ensure_db(db)
        assert revive_entry("does-not-exist", db_path=db) is False


class TestV2ToV3Migration:
    """ENH-3416: v2 -> v3 adds attempt/next_attempt_at to queue_entries."""

    def test_v2_to_v3_migration(self, tmp_path: Path) -> None:
        db = tmp_path / "queue.db"
        from little_loops.queue_store import _MIGRATIONS

        conn = sqlite3.connect(str(db))
        try:
            for script in _MIGRATIONS[:2]:
                conn.executescript(script)
            conn.execute("INSERT OR IGNORE INTO meta(key, value) VALUES('schema_version', '2')")
            conn.commit()
        finally:
            conn.close()

        ensure_db(db)

        conn = sqlite3.connect(str(db))
        try:
            version = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
            columns = {row[1] for row in conn.execute("PRAGMA table_info(queue_entries)")}
        finally:
            conn.close()

        assert int(version[0]) == SCHEMA_VERSION
        assert {"attempt", "next_attempt_at"}.issubset(columns)

    def test_pre_existing_rows_read_back_with_attempt_zero(self, tmp_path: Path) -> None:
        db = tmp_path / "queue.db"
        from little_loops.queue_store import _MIGRATIONS

        conn = sqlite3.connect(str(db))
        try:
            for script in _MIGRATIONS[:2]:
                conn.executescript(script)
            conn.execute("INSERT OR IGNORE INTO meta(key, value) VALUES('schema_version', '2')")
            conn.execute(
                "INSERT INTO queue_entries(id, action, enqueued_at, priority, status, result) "
                "VALUES ('legacy', '{}', '2026-01-01T00:00:00Z', 3, 'pending', NULL)"
            )
            conn.commit()
        finally:
            conn.close()

        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            row = conn.execute(
                "SELECT attempt, next_attempt_at FROM queue_entries WHERE id = 'legacy'"
            ).fetchone()
        finally:
            conn.close()
        assert row[0] == 0
        assert row[1] is None


class TestConnect:
    def test_returns_row_factory_connection(self, tmp_path: Path) -> None:
        db = tmp_path / "queue.db"
        conn = connect(db)
        try:
            assert conn.row_factory is sqlite3.Row
        finally:
            conn.close()


class TestV1ToV2Migration:
    """FEAT-2930: v1 -> v2 adds claimed_at/owner_pid to queue_entries."""

    def test_v1_to_v2_migration(self, tmp_path: Path) -> None:
        """Manually bootstrap a v1 schema, then verify ensure_db() applies the v2 migration."""
        db = tmp_path / "queue.db"
        from little_loops.queue_store import _MIGRATIONS

        conn = sqlite3.connect(str(db))
        try:
            conn.executescript(_MIGRATIONS[0])
            conn.execute("INSERT OR IGNORE INTO meta(key, value) VALUES('schema_version', '1')")
            conn.commit()
        finally:
            conn.close()

        ensure_db(db)

        conn = sqlite3.connect(str(db))
        try:
            version = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
            columns = {row[1] for row in conn.execute("PRAGMA table_info(queue_entries)")}
        finally:
            conn.close()

        assert int(version[0]) == SCHEMA_VERSION
        assert {"claimed_at", "owner_pid"}.issubset(columns)

    def test_claim_entry_populates_new_columns(self, tmp_path: Path) -> None:
        db = tmp_path / "queue.db"
        entry = add_entry(_spec(), db_path=db)
        assert claim_entry(entry.id, db_path=db, owner_pid=4242) is True
        claimed = get_entry(entry.id, db)
        assert claimed is not None
        assert claimed.owner_pid == 4242
        assert claimed.claimed_at is not None

    def test_update_entry_result_clears_owner_columns(self, tmp_path: Path) -> None:
        db = tmp_path / "queue.db"
        entry = add_entry(_spec(), db_path=db)
        claim_entry(entry.id, db_path=db, owner_pid=4242)
        update_entry_result(entry.id, "done", {"exit_code": 0}, db_path=db)
        done = get_entry(entry.id, db)
        assert done is not None
        assert done.owner_pid is None
        assert done.claimed_at is None


class TestResetToPending:
    def test_resets_running_entry(self, tmp_path: Path) -> None:
        db = tmp_path / "queue.db"
        entry = add_entry(_spec(), db_path=db)
        claim_entry(entry.id, db_path=db, owner_pid=4242)
        assert reset_to_pending(entry.id, db_path=db) is True
        reset = get_entry(entry.id, db)
        assert reset is not None
        assert reset.status == "pending"
        assert reset.owner_pid is None
        assert reset.claimed_at is None

    def test_does_not_touch_attempt_or_next_attempt_at(self, tmp_path: Path) -> None:
        """reset_to_pending is the reclaim path, not the backoff path (ENH-3416):
        an owner death is a slot to refill, not a backoff-eligible failure."""
        db = tmp_path / "queue.db"
        entry = add_entry(_spec(), db_path=db)
        claim_entry(entry.id, db_path=db, owner_pid=4242)
        assert get_entry(entry.id, db).attempt == 1

        reset_to_pending(entry.id, db_path=db)
        reset = get_entry(entry.id, db)
        assert reset is not None
        assert reset.attempt == 1
        assert reset.next_attempt_at is None

    def test_leaves_non_running_entry_untouched(self, tmp_path: Path) -> None:
        db = tmp_path / "queue.db"
        entry = add_entry(_spec(), db_path=db)  # still pending
        assert reset_to_pending(entry.id, db_path=db) is False
        assert get_entry(entry.id, db).status == "pending"  # type: ignore[union-attr]

    def test_returns_false_for_unknown_id(self, tmp_path: Path) -> None:
        db = tmp_path / "queue.db"
        ensure_db(db)
        assert reset_to_pending("does-not-exist", db_path=db) is False
