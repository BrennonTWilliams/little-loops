"""Tests for little_loops.session_store — writers module."""

from __future__ import annotations

import itertools
import json
import re
import sqlite3
from pathlib import Path

import pytest

from little_loops.session_store import (
    SCHEMA_VERSION,
    SQLiteTransport,
    _derive_transition,
    cli_event_context,
    connect,
    ensure_db,
    fts_phrase,
    is_correction,
    recent,
    record_correction,
    search,
)
from little_loops.transport import Transport

# ENH-2529: consolidate per-test temp dirs under one module-scoped parent to cut
# macOS launchservicesd/mds re-indexing churn during full-suite runs. Each test
# still gets a fresh, unique directory; only the parent dir consolidates.
_TMP_COUNTER = itertools.count()


@pytest.fixture(scope="module")
def _module_tmp_parent(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One temp parent per module instead of one top-level dir per test."""
    return tmp_path_factory.mktemp("session_store")


@pytest.fixture
def tmp_path(_module_tmp_parent: Path, request: pytest.FixtureRequest) -> Path:
    """Override built-in tmp_path: unique fresh subdir of the module parent."""
    name = re.sub(r"\W", "_", request.node.name)[:30]
    path = _module_tmp_parent / f"{name}_{next(_TMP_COUNTER)}"
    path.mkdir()
    return path


class TestSQLiteTransport:
    """The SQLiteTransport EventBus sink."""

    def test_satisfies_transport_protocol(self, tmp_path: Path) -> None:
        transport = SQLiteTransport(tmp_path / "session.db")
        assert isinstance(transport, Transport)
        transport.close()

    def test_records_loop_event(self, tmp_path: Path) -> None:
        db = tmp_path / "session.db"
        transport = SQLiteTransport(db)
        transport.send({"event": "state_enter", "loop_name": "docs-sync", "state": "verify"})
        transport.close()
        rows = recent(db, kind="loop")
        assert len(rows) == 1
        assert rows[0]["loop_name"] == "docs-sync"
        assert rows[0]["transition"] == "state_enter"

    def test_ignores_unrecognized_event(self, tmp_path: Path) -> None:
        db = tmp_path / "session.db"
        transport = SQLiteTransport(db)
        transport.send({"event": "action_output", "loop_name": "x"})
        transport.close()
        assert recent(db, kind="loop") == []

    def test_loop_complete_records_mapped_final_status_as_state(self, tmp_path: Path) -> None:
        """BUG-3066: state derives from terminated_by/failure_terminal via map_final_status,
        not a phantom 'outcome' key production never emits."""
        db = tmp_path / "session.db"
        transport = SQLiteTransport(db)
        transport.send(
            {
                "event": "loop_complete",
                "loop_name": "x",
                "terminated_by": "terminal",
                "failure_terminal": False,
            }
        )
        transport.close()
        assert recent(db, kind="loop")[0]["state"] == "completed"

    def test_loop_complete_records_non_null_state_on_failure(self, tmp_path: Path) -> None:
        """BUG-3066 AC 6: a crashed run must not leave state NULL in the session store."""
        db = tmp_path / "session.db"
        transport = SQLiteTransport(db)
        transport.send({"event": "loop_complete", "loop_name": "x", "terminated_by": "error"})
        transport.close()
        row = recent(db, kind="loop")[0]
        assert row["state"] is not None
        assert row["state"] == "failed"

    def test_send_after_close_is_noop(self, tmp_path: Path) -> None:
        db = tmp_path / "session.db"
        transport = SQLiteTransport(db)
        transport.close()
        transport.send({"event": "state_enter", "loop_name": "x"})  # must not raise

    def test_close_is_idempotent(self, tmp_path: Path) -> None:
        transport = SQLiteTransport(tmp_path / "session.db")
        transport.close()
        transport.close()  # must not raise


class TestDeriveTransition:
    """_derive_transition() maps issue event types to canonical status strings."""

    def test_known_mappings(self) -> None:
        cases = [
            ("issue.completed", "done"),
            ("issue.closed", "done"),
            ("issue.deferred", "deferred"),
            ("issue.skipped", "cancelled"),
            ("issue.created", "open"),
            ("issue.started", "in_progress"),
        ]
        for event_type, expected in cases:
            assert _derive_transition(event_type) == expected, event_type

    def test_unknown_event_falls_back_to_suffix(self) -> None:
        assert _derive_transition("issue.failure_captured") == "failure_captured"
        assert _derive_transition("issue.reopened") == "reopened"


class TestSQLiteTransportIssueEvents:
    """SQLiteTransport records issue.* events into issue_events (ENH-1690)."""

    def test_records_issue_completed_event(self, tmp_path: Path) -> None:
        db = tmp_path / "session.db"
        transport = SQLiteTransport(db)
        transport.send(
            {
                "event": "issue.completed",
                "ts": "2026-05-24T12:00:00Z",
                "issue_id": "ENH-99",
                "issue_type": "ENH",
                "priority": "P2",
            }
        )
        transport.close()
        rows = recent(db, kind="issue")
        assert len(rows) == 1
        assert rows[0]["issue_id"] == "ENH-99"
        assert rows[0]["transition"] == "done"

    def test_issue_event_transition_mapping(self, tmp_path: Path) -> None:
        db = tmp_path / "session.db"
        transport = SQLiteTransport(db)
        events = [
            ("issue.completed", "done"),
            ("issue.deferred", "deferred"),
            ("issue.skipped", "cancelled"),
            ("issue.created", "open"),
            ("issue.started", "in_progress"),
        ]
        for event_type, _ in events:
            transport.send({"event": event_type, "ts": "2026-05-24T12:00:00Z", "issue_id": "X-1"})
        transport.close()
        rows = recent(db, kind="issue", limit=10)
        transitions = {r["transition"] for r in rows}
        for _, expected in events:
            assert expected in transitions

    def test_loop_event_does_not_create_issue_row(self, tmp_path: Path) -> None:
        db = tmp_path / "session.db"
        transport = SQLiteTransport(db)
        transport.send({"event": "state_enter", "loop_name": "x", "state": "s"})
        transport.close()
        assert recent(db, kind="issue") == []

    def test_issue_event_is_fts_searchable(self, tmp_path: Path) -> None:
        db = tmp_path / "session.db"
        transport = SQLiteTransport(db)
        transport.send(
            {
                "event": "issue.completed",
                "ts": "2026-05-24T12:00:00Z",
                "issue_id": "ENH-1690",
                "issue_type": "ENH",
            }
        )
        transport.close()
        # FTS5 tokenizes "ENH-1690" as ["ENH", "1690"]; search the numeric token
        results = search(db, query="1690")
        assert any(r["kind"] == "issue" for r in results)

    def test_unrecognized_event_not_recorded_as_issue(self, tmp_path: Path) -> None:
        db = tmp_path / "session.db"
        transport = SQLiteTransport(db)
        transport.send({"event": "action_output", "issue_id": "X-1"})
        transport.close()
        assert recent(db, kind="issue") == []

    def test_issue_event_captured_at_round_trip(self, tmp_path: Path) -> None:
        """captured_at in send() dict is stored and retrieved from issue_events."""
        db = tmp_path / "session.db"
        transport = SQLiteTransport(db)
        transport.send(
            {
                "event": "issue.completed",
                "ts": "2026-05-20T10:00:00Z",
                "issue_id": "ENH-1839",
                "captured_at": "2026-05-20T10:00:00Z",
            }
        )
        transport.close()
        conn = connect(db)
        try:
            rows = conn.execute(
                "SELECT captured_at FROM issue_events WHERE issue_id = ?", ("ENH-1839",)
            ).fetchall()
        finally:
            conn.close()
        assert len(rows) == 1
        assert rows[0]["captured_at"] == "2026-05-20T10:00:00Z"

    def test_bare_numeric_issue_id_canonicalized_via_file_path(self, tmp_path: Path) -> None:
        """BUG-2769: a bare-numeric issue_id is canonicalized using the event's file_path."""
        issue_file = tmp_path / "P2-BUG-2756-bare-int-id.md"
        issue_file.write_text("---\nid: 2756\nstatus: done\n---\n# x\n", encoding="utf-8")
        db = tmp_path / "session.db"
        transport = SQLiteTransport(db)
        transport.send(
            {
                "event": "issue.completed",
                "ts": "2026-05-24T12:00:00Z",
                "issue_id": "2756",
                "file_path": str(issue_file),
            }
        )
        transport.close()
        conn = connect(db)
        try:
            rows = conn.execute(
                "SELECT issue_id FROM issue_events WHERE issue_id = 'BUG-2756'"
            ).fetchall()
        finally:
            conn.close()
        assert len(rows) == 1


class TestIsCorrectionHeuristic:
    """ENH-1831: correction-detection heuristic."""

    @pytest.mark.parametrize(
        "text",
        [
            "no, don't do that",
            "stop doing that",
            "revert that last change",
            "don't add comments",
            "No! That's wrong",
            "that's wrong, try again",
            "use snake_case instead",
            "actually that function is in utils.py",
            "you missed the import",
            "should be wrapped in a try/except",
            "remember that we always use dataclasses",
            "never use bare except clauses",
            "from now on always add type hints",
            "!remember always use snake_case",
            "!Remember use absolute imports",
            "wrong approach, use a generator",
        ],
    )
    def test_true_positives(self, text: str) -> None:
        assert is_correction(text), f"expected correction signal: {text!r}"

    @pytest.mark.parametrize(
        "text",
        [
            "no problem",
            "sounds good",
            "noted, thanks",
            "implement the login feature",
            "fix the authentication bug",
            "noted",
            "that should be fine",
            "use it as-is",
            "this is actually a great idea",
            "never mind, good work",
            "I'm always happy with this approach",
        ],
    )
    def test_true_negatives(self, text: str) -> None:
        assert not is_correction(text), f"expected non-correction: {text!r}"

    def test_extra_patterns_fire(self) -> None:
        assert is_correction("not quite what I wanted", extra_patterns=["not quite"])

    def test_extra_patterns_do_not_replace_builtins(self) -> None:
        assert is_correction("no, that's wrong", extra_patterns=["not quite"])

    def test_extra_patterns_empty(self) -> None:
        assert is_correction("no, don't do that", extra_patterns=[]) == is_correction(
            "no, don't do that"
        )
        assert not is_correction("sounds good", extra_patterns=[])


class TestRecordCorrection:
    """ENH-1831: record_correction() DB write round-trip."""

    def test_record_correction_roundtrip(self, tmp_path: Path) -> None:
        from little_loops.session_store import recent

        db = tmp_path / "session.db"
        record_correction(db, "sess-r1", "no, don't do that", "user_prompt_submit")
        rows = recent(db, kind="correction")
        assert len(rows) == 1
        assert rows[0]["content"] == "no, don't do that"
        assert rows[0]["source"] == "user_prompt_submit"

    def test_record_correction_truncates_to_512(self, tmp_path: Path) -> None:
        from little_loops.session_store import recent

        db = tmp_path / "session.db"
        long_text = "stop " + "x" * 600
        record_correction(db, None, long_text, "user_prompt_submit")
        rows = recent(db, kind="correction")
        assert len(rows[0]["content"]) <= 512

    def test_record_correction_fts_indexed(self, tmp_path: Path) -> None:
        from little_loops.session_store import search

        db = tmp_path / "session.db"
        record_correction(db, "sess-r2", "revert that last commit", "user_prompt_submit")
        results = search(db, query="revert")
        assert any(r["kind"] == "correction" for r in results)

    def test_record_correction_gate_disabled(self, tmp_path: Path) -> None:
        """capture.corrections: false suppresses write regardless of call site."""
        from little_loops.session_store import recent

        db = tmp_path / "session.db"
        record_correction(
            db,
            "sess-g1",
            "no, stop",
            "user_prompt_submit",
            config={"analytics": {"capture": {"corrections": False}}},
        )
        rows = recent(db, kind="correction")
        assert len(rows) == 0, "record_correction must be a no-op when capture.corrections is false"

    def test_write_file_event_gate_disabled(self, tmp_path: Path) -> None:
        """capture.file_events: false suppresses write regardless of call site."""
        from little_loops.session_store import recent, write_file_event

        db = tmp_path / "session.db"
        write_file_event(
            db,
            "sess-g2",
            "scripts/foo.py",
            "Read",
            config={"analytics": {"capture": {"file_events": False}}},
        )
        rows = recent(db, kind="file")
        assert len(rows) == 0, "write_file_event must be a no-op when capture.file_events is false"


class TestRecordSkillEvent:
    """ENH-1833: record_skill_event() DB write round-trip."""

    def test_record_skill_event_roundtrip(self, tmp_path: Path) -> None:
        from little_loops.session_store import recent, record_skill_event

        db = tmp_path / "session.db"
        record_skill_event(db, "sess-s1", "refine-issue", "ENH-1833")
        rows = recent(db, kind="skill")
        assert len(rows) == 1
        assert rows[0]["skill_name"] == "refine-issue"
        assert rows[0]["args"] == "ENH-1833"
        assert rows[0]["session_id"] == "sess-s1"

    def test_record_skill_event_truncates_args_to_200(self, tmp_path: Path) -> None:
        from little_loops.session_store import recent, record_skill_event

        db = tmp_path / "session.db"
        long_args = "x" * 300
        record_skill_event(db, None, "capture-issue", long_args)
        rows = recent(db, kind="skill")
        assert len(rows[0]["args"]) <= 200

    def test_record_skill_event_fts_indexed(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_skill_event, search

        db = tmp_path / "session.db"
        record_skill_event(db, "sess-s2", "ready-issue", "")
        # FTS5 tokenises hyphens, so query on individual word "ready"
        results = search(db, query="ready")
        assert any(r["kind"] == "skill" for r in results)

    def test_record_skill_event_config_stub_accepted(self, tmp_path: Path) -> None:
        """An empty capture config is permissive (skills defaults to ["*"]); no suppression."""
        from little_loops.session_store import recent, record_skill_event

        db = tmp_path / "session.db"
        record_skill_event(db, "sess-s3", "check-code", "", config={"analytics": {}})
        rows = recent(db, kind="skill")
        assert len(rows) == 1, "permissive default capture.skills must not suppress the write"

    def test_record_skill_event_gate_disabled(self, tmp_path: Path) -> None:
        """capture.skills narrowed to exclude skill_name suppresses the write."""
        from little_loops.session_store import recent, record_skill_event

        db = tmp_path / "session.db"
        record_skill_event(
            db,
            "sess-s4",
            "check-code",
            "",
            config={"analytics": {"capture": {"skills": ["other-skill"]}}},
        )
        rows = recent(db, kind="skill")
        assert len(rows) == 0, "record_skill_event must be a no-op when capture.skills excludes it"


class TestCliEventContext:
    """ENH-1848: cli_event_context() DB write round-trip and mechanics."""

    def test_cli_event_roundtrip(self, tmp_path: Path) -> None:
        db = tmp_path / "session.db"
        with cli_event_context(db, binary="ll-refine-issue", args=["ENH-1848"]):
            pass
        rows = recent(db, kind="cli")
        assert len(rows) == 1
        assert rows[0]["binary"] == "ll-refine-issue"
        assert json.loads(rows[0]["args"]) == ["ENH-1848"]
        assert rows[0]["exit_code"] == 0
        assert rows[0]["duration_ms"] is not None

    def test_cli_event_exception_exit(self, tmp_path: Path) -> None:
        db = tmp_path / "session.db"
        with pytest.raises(ValueError):
            with cli_event_context(db, binary="ll-check-code", args=[]):
                raise ValueError("simulated failure")
        rows = recent(db, kind="cli")
        assert len(rows) == 1
        assert rows[0]["exit_code"] == 1

    def test_cli_event_duration_accuracy(self, tmp_path: Path) -> None:
        db = tmp_path / "session.db"
        with cli_event_context(db, binary="ll-session", args=["recent"]):
            pass
        rows = recent(db, kind="cli")
        assert rows[0]["duration_ms"] is not None
        assert isinstance(rows[0]["duration_ms"], int)
        assert rows[0]["duration_ms"] >= 0

    def test_schema_v8_cli_events_table_exists(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            names = {
                r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
        finally:
            conn.close()
        assert "cli_events" in names
        assert SCHEMA_VERSION == 45
        assert int(row[0]) == 45

    def test_cli_event_context_respects_LL_HISTORY_DB(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """LL_HISTORY_DB env var must redirect DB writes when the default path is used."""
        from little_loops.session_store import DEFAULT_DB_PATH

        isolated_db = tmp_path / "isolated.db"
        monkeypatch.setenv("LL_HISTORY_DB", str(isolated_db))
        with cli_event_context(DEFAULT_DB_PATH, binary="ll-test-env-var", args=["--check"]):
            pass
        rows = recent(isolated_db, kind="cli")
        assert len(rows) == 1
        assert rows[0]["binary"] == "ll-test-env-var"

    def test_cli_event_locked_db_does_not_crash_body(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A locked/unavailable DB on enter must not block the wrapped command.

        Regression: cli_event_context wraps ~20+ ll-* entry points; an unguarded
        ``INSERT INTO cli_events`` that raised ``OperationalError: database is
        locked`` used to crash the entire command before it did any work. The
        analytics row must be skipped (EPIC-1707 graceful degradation) while the
        body still runs.
        """
        import little_loops.session_store as ss

        def _locked_connect(*_a: object, **_k: object) -> sqlite3.Connection:
            raise sqlite3.OperationalError("database is locked")

        monkeypatch.setattr(ss, "connect", _locked_connect)

        db = tmp_path / "session.db"
        ran = False
        with cli_event_context(db, binary="ll-issues", args=["show", "2701"]):
            ran = True
        assert ran, "wrapped command body must run even when the analytics INSERT fails"

    def test_cli_event_locked_exit_update_does_not_mask_success(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A lock on the exit UPDATE must not raise out of a successful command."""
        import little_loops.session_store as ss

        real_connect = ss.connect

        class _FailUpdateConn:
            def __init__(self, inner: sqlite3.Connection) -> None:
                self._inner = inner

            def execute(self, sql: str, *params: object) -> object:
                if sql.startswith("UPDATE cli_events"):
                    raise sqlite3.OperationalError("database is locked")
                return self._inner.execute(sql, *params)

            def __getattr__(self, name: str) -> object:
                return getattr(self._inner, name)

        def _wrapped_connect(*a: object, **k: object) -> object:
            return _FailUpdateConn(real_connect(*a, **k))

        monkeypatch.setattr(ss, "connect", _wrapped_connect)

        db = tmp_path / "session.db"
        ran = False
        with cli_event_context(db, binary="ll-issues", args=["show", "2701"]):
            ran = True
        assert ran, "command body must complete even when the exit UPDATE fails"

    def test_cli_event_context_explicit_path_not_redirected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An explicit path passed to cli_event_context must not be overridden by LL_HISTORY_DB."""

        explicit_db = tmp_path / "explicit.db"
        env_db = tmp_path / "env.db"
        monkeypatch.setenv("LL_HISTORY_DB", str(env_db))
        # Pass a path that is NOT DEFAULT_DB_PATH — must write to explicit_db
        with cli_event_context(explicit_db, binary="ll-explicit", args=[]):
            pass
        rows = recent(explicit_db, kind="cli")
        assert len(rows) == 1
        assert rows[0]["binary"] == "ll-explicit"
        # env_db must be empty (not written to)
        assert not env_db.exists()

    def test_cli_event_context_gate_disabled(self, tmp_path: Path) -> None:
        """capture.cli_commands narrowed to exclude binary suppresses the row write."""
        db = tmp_path / "session.db"
        ran = False
        with cli_event_context(
            db,
            binary="ll-issues",
            args=["show", "2701"],
            config={"analytics": {"capture": {"cli_commands": ["not-this-binary"]}}},
        ):
            ran = True
        assert ran, "wrapped command body must run even when the cli_commands gate excludes it"
        rows = recent(db, kind="cli")
        assert len(rows) == 0, "cli_event_context must skip the row write when gated off"


class TestMineCorrectionsFromMessages:
    """Unit tests for mine_corrections_from_messages() (ENH-1904)."""

    def test_mines_corrections_from_existing_message_events(self, tmp_path: Path) -> None:
        """mine_corrections_from_messages picks up pre-existing message_events rows."""
        from little_loops.session_store import connect as ss_connect
        from little_loops.session_store import mine_corrections_from_messages

        db = tmp_path / "session.db"
        conn = ss_connect(db)
        try:
            conn.execute(
                "INSERT INTO message_events(ts, session_id, content) VALUES(?, ?, ?)",
                ("2026-06-03T10:00:00Z", "s-mine", "no, don't do that"),
            )
            conn.commit()
            count = mine_corrections_from_messages(conn)
            conn.commit()
            assert count == 1
        finally:
            conn.close()
        rows = recent(db, kind="correction")
        assert len(rows) == 1
        assert rows[0]["session_id"] == "s-mine"

    def test_mine_corrections_idempotent(self, tmp_path: Path) -> None:
        """Calling mine_corrections_from_messages twice produces exactly 1 row."""
        from little_loops.session_store import connect as ss_connect
        from little_loops.session_store import mine_corrections_from_messages

        db = tmp_path / "session.db"
        conn = ss_connect(db)
        try:
            conn.execute(
                "INSERT INTO message_events(ts, session_id, content) VALUES(?, ?, ?)",
                ("2026-06-03T10:00:00Z", "s-idem2", "no, don't do that"),
            )
            conn.commit()
            mine_corrections_from_messages(conn)
            conn.commit()
            mine_corrections_from_messages(conn)
            conn.commit()
        finally:
            conn.close()
        assert len(recent(db, kind="correction")) == 1

    def test_mine_corrections_gate_disabled(self, tmp_path: Path) -> None:
        """mine_corrections_from_messages respects analytics.capture.corrections gate."""
        from little_loops.session_store import connect as ss_connect
        from little_loops.session_store import mine_corrections_from_messages

        db = tmp_path / "session.db"
        conn = ss_connect(db)
        try:
            conn.execute(
                "INSERT INTO message_events(ts, session_id, content) VALUES(?, ?, ?)",
                ("2026-06-03T10:00:00Z", "s-gated", "no, don't do that"),
            )
            conn.commit()
            count = mine_corrections_from_messages(
                conn, config={"analytics": {"capture": {"corrections": False}}}
            )
            conn.commit()
            assert count == 0
        finally:
            conn.close()
        assert len(recent(db, kind="correction")) == 0


class TestRecordIssueSnapshot:
    """ENH-2151: record_issue_snapshot() DB write round-trip."""

    def _make_issue_file(self, directory: Path, issue_id: str, title: str, status: str) -> Path:
        path = directory / f"P2-{issue_id}-test.md"
        path.write_text(
            f"---\nid: {issue_id}\ntype: ENH\npriority: P2\nstatus: {status}\n"
            f"title: {title}\n---\n\n# {title}\n\nBody text for {issue_id}.",
            encoding="utf-8",
        )
        return path

    def test_record_issue_snapshot_roundtrip(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_issue_snapshot

        db = tmp_path / "history.db"
        issue_file = self._make_issue_file(tmp_path, "ENH-2151", "Store snapshots", "done")

        record_issue_snapshot(db, "ENH-2151", "done", str(issue_file))

        conn = connect(db)
        try:
            row = conn.execute("SELECT * FROM issue_snapshots WHERE issue_id='ENH-2151'").fetchone()
        finally:
            conn.close()
        assert row is not None
        assert row["issue_id"] == "ENH-2151"
        assert row["transition"] == "done"
        assert row["title"] == "Store snapshots"
        assert "Body text for ENH-2151" in (row["body"] or "")

    def test_record_issue_snapshot_fts_indexed(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_issue_snapshot, search

        db = tmp_path / "history.db"
        issue_file = self._make_issue_file(tmp_path, "ENH-2151", "Store snapshots", "done")
        record_issue_snapshot(db, "ENH-2151", "done", str(issue_file))

        results = search(db, query="snapshots")
        assert any(r["kind"] == "snapshot" for r in results)

    def test_record_issue_snapshot_idempotent(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_issue_snapshot

        db = tmp_path / "history.db"
        issue_file = self._make_issue_file(tmp_path, "ENH-2151", "Store snapshots", "done")

        record_issue_snapshot(db, "ENH-2151", "done", str(issue_file))
        record_issue_snapshot(db, "ENH-2151", "done", str(issue_file))  # duplicate

        conn = connect(db)
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM issue_snapshots WHERE issue_id='ENH-2151' AND transition='done'"
            ).fetchone()[0]
        finally:
            conn.close()
        assert count == 1, "INSERT OR IGNORE must deduplicate on (issue_id, transition)"

    def test_record_issue_snapshot_retype_stays_silent(self, tmp_path: Path, caplog) -> None:
        """Identical-id re-insert (retype/repeat) is a true idempotent no-op: no warning."""
        import logging

        from little_loops.session_store import record_issue_snapshot

        db = tmp_path / "history.db"
        issue_file = self._make_issue_file(tmp_path, "ENH-2151", "Store snapshots", "done")

        with caplog.at_level(logging.WARNING, logger="little_loops.session_store.writers"):
            record_issue_snapshot(db, "ENH-2151", "done", str(issue_file))
            record_issue_snapshot(db, "ENH-2151", "done", str(issue_file))

        assert "dedup collision" not in caplog.text

    def test_record_issue_snapshot_number_reuse_warns(self, tmp_path: Path, caplog) -> None:
        """BUG-3006: two distinct issues reusing a bare number collide silently unless warned."""
        import logging

        from little_loops.session_store import record_issue_snapshot

        db = tmp_path / "history.db"
        first_file = self._make_issue_file(tmp_path, "BUG-9001", "First", "done")
        second_file = tmp_path / "P2-EPIC-9001-second.md"
        second_file.write_text(
            "---\nid: EPIC-9001\ntype: EPIC\npriority: P2\nstatus: done\n"
            "title: Second\n---\n\n# Second\n\nBody text.",
            encoding="utf-8",
        )

        with caplog.at_level(logging.WARNING, logger="little_loops.session_store.writers"):
            record_issue_snapshot(db, "BUG-9001", "done", str(first_file))
            record_issue_snapshot(db, "EPIC-9001", "done", str(second_file))

        assert "dedup collision" in caplog.text
        assert "BUG-9001" in caplog.text
        assert "EPIC-9001" in caplog.text

        conn = connect(db)
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM issue_snapshots WHERE issue_num=9001 AND transition='done'"
            ).fetchone()[0]
        finally:
            conn.close()
        assert count == 1, "the second issue's row is still discarded — only the warning is new"

    def test_record_issue_snapshot_missing_file_is_noop(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_issue_snapshot

        db = tmp_path / "history.db"
        record_issue_snapshot(db, "ENH-9999", "done", str(tmp_path / "nonexistent.md"))

        conn = connect(db)
        try:
            count = conn.execute("SELECT COUNT(*) FROM issue_snapshots").fetchone()[0]
        finally:
            conn.close()
        assert count == 0, "Missing file should produce no rows"


class TestRecordIssueEvent:
    """BUG-2770: record_issue_event() DB write round-trip."""

    def test_record_issue_event_roundtrip(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_issue_event

        db = tmp_path / "history.db"
        record_issue_event(
            db,
            "ENH-2151",
            "done",
            session_id="sess-abc",
            issue_type="ENH",
            priority="P2",
            discovered_by="scan-codebase",
            captured_at="2026-07-24T00:00:00Z",
            completed_at="2026-07-24T12:00:00Z",
        )

        conn = connect(db)
        try:
            row = conn.execute("SELECT * FROM issue_events WHERE issue_id='ENH-2151'").fetchone()
        finally:
            conn.close()
        assert row is not None
        assert row["issue_id"] == "ENH-2151"
        assert row["transition"] == "done"
        assert row["session_id"] == "sess-abc"
        assert row["issue_type"] == "ENH"
        assert row["priority"] == "P2"
        assert row["discovered_by"] == "scan-codebase"
        assert row["captured_at"] == "2026-07-24T00:00:00Z"
        assert row["completed_at"] == "2026-07-24T12:00:00Z"

    def test_record_issue_event_read_via_recent(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_issue_event

        db = tmp_path / "history.db"
        record_issue_event(db, "ENH-2151", "done", session_id="sess-abc", issue_type="ENH")

        rows = recent(db, kind="issue")
        assert len(rows) == 1
        assert rows[0]["issue_id"] == "ENH-2151"
        assert rows[0]["transition"] == "done"

    def test_record_issue_event_idempotent(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_issue_event

        db = tmp_path / "history.db"
        record_issue_event(db, "ENH-2151", "done")
        record_issue_event(db, "ENH-2151", "done")  # duplicate

        conn = connect(db)
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM issue_events WHERE issue_id='ENH-2151' AND transition='done'"
            ).fetchone()[0]
        finally:
            conn.close()
        assert count == 1, "INSERT OR IGNORE must deduplicate on (issue_id, transition)"

    def test_record_issue_event_retype_stays_silent(self, tmp_path: Path, caplog) -> None:
        """Identical-id re-insert (retype/repeat) is a true idempotent no-op: no warning."""
        import logging

        from little_loops.session_store import record_issue_event

        db = tmp_path / "history.db"
        with caplog.at_level(logging.WARNING, logger="little_loops.session_store.writers"):
            record_issue_event(db, "ENH-9002", "done")
            record_issue_event(db, "ENH-9002", "done")

        assert "dedup collision" not in caplog.text

    def test_record_issue_event_number_reuse_warns(self, tmp_path: Path, caplog) -> None:
        """BUG-3006: reported repro — EPIC-9001's done transition is discarded after BUG-9001's."""
        import logging

        from little_loops.session_store import record_issue_event

        db = tmp_path / "history.db"
        with caplog.at_level(logging.WARNING, logger="little_loops.session_store.writers"):
            record_issue_event(db, "BUG-9001", "done")
            record_issue_event(db, "EPIC-9001", "done")

        assert "dedup collision" in caplog.text
        assert "BUG-9001" in caplog.text
        assert "EPIC-9001" in caplog.text

        conn = connect(db)
        try:
            row = conn.execute(
                "SELECT issue_id FROM issue_events WHERE issue_num=9001 AND transition='done'"
            ).fetchone()
        finally:
            conn.close()
        assert row["issue_id"] == "BUG-9001", "EPIC-9001's completion was silently discarded"


class TestSkillEventContext:
    """ENH-2460: skill_event_context() insert-then-update round-trip."""

    def test_success_path_populates_completion_columns(self, tmp_path: Path) -> None:
        from little_loops.session_store import skill_event_context

        db = tmp_path / "history.db"
        with skill_event_context(db, "sess-1", "refine-issue", "ENH-2460"):
            pass
        rows = recent(db, kind="skill")
        assert len(rows) == 1
        assert rows[0]["skill_name"] == "refine-issue"
        assert rows[0]["exit_code"] == 0
        assert rows[0]["success"] == 1
        assert rows[0]["duration_ms"] is not None
        assert rows[0]["duration_ms"] >= 0

    def test_raise_path_records_failure(self, tmp_path: Path) -> None:
        from little_loops.session_store import skill_event_context

        db = tmp_path / "history.db"
        with pytest.raises(ValueError):
            with skill_event_context(db, "sess-2", "check-code", ""):
                raise ValueError("boom")
        rows = recent(db, kind="skill")
        assert rows[0]["exit_code"] == 1
        assert rows[0]["success"] == 0

    def test_host_provided_exit_code_wins(self, tmp_path: Path) -> None:
        from little_loops.session_store import skill_event_context

        db = tmp_path / "history.db"
        with skill_event_context(db, None, "manage-issue", "") as completion:
            completion.exit_code = 3
        rows = recent(db, kind="skill")
        assert rows[0]["exit_code"] == 3
        assert rows[0]["success"] == 0

    def test_args_truncated_to_200(self, tmp_path: Path) -> None:
        from little_loops.session_store import skill_event_context

        db = tmp_path / "history.db"
        with skill_event_context(db, None, "capture-issue", "x" * 300):
            pass
        rows = recent(db, kind="skill")
        assert len(rows[0]["args"]) <= 200

    def test_fts_indexed(self, tmp_path: Path) -> None:
        from little_loops.session_store import skill_event_context

        db = tmp_path / "history.db"
        with skill_event_context(db, "sess-3", "ready-issue", ""):
            pass
        results = search(db, query="ready")
        assert any(r["kind"] == "skill" for r in results)

    def test_best_effort_on_unopenable_db(self, tmp_path: Path) -> None:
        """A db path that cannot be opened must not prevent the body from running."""
        from little_loops.session_store import skill_event_context

        ran = False
        # tmp_path is a directory — sqlite cannot open it as a database file.
        with skill_event_context(tmp_path, None, "broken-db-skill", ""):
            ran = True
        assert ran

    def test_config_permissive_default_still_writes(self, tmp_path: Path) -> None:
        """An empty capture config is permissive (skills defaults to ["*"]); row still written."""
        from little_loops.session_store import skill_event_context

        db = tmp_path / "history.db"
        with skill_event_context(
            db, "sess-4", "check-code", "", config={"analytics": {}}
        ) as completion:
            pass
        assert completion.exit_code == 0
        rows = recent(db, kind="skill")
        assert len(rows) == 1

    def test_gate_disabled_still_yields_completion(self, tmp_path: Path) -> None:
        """capture.skills narrowed to exclude skill_name still yields a completion, skips write."""
        from little_loops.session_store import SkillEventCompletion, skill_event_context

        db = tmp_path / "history.db"
        with skill_event_context(
            db,
            "sess-5",
            "check-code",
            "",
            config={"analytics": {"capture": {"skills": ["other-skill"]}}},
        ) as completion:
            assert isinstance(completion, SkillEventCompletion)
        rows = recent(db, kind="skill")
        assert len(rows) == 0, "skill_event_context must skip the row write when gated off"


class TestInferIssueId:
    """ENH-2458: _infer_issue_id() message/branch parsing."""

    def test_typed_closes_reference(self) -> None:
        from little_loops.session_store import _infer_issue_id

        assert _infer_issue_id("fix: something\n\nCloses ENH-2458") == "ENH-2458"

    def test_fixes_hash_reference_falls_back_to_typed_token(self) -> None:
        from little_loops.session_store import _infer_issue_id

        # "#123" has no type prefix; a typed token elsewhere wins.
        assert _infer_issue_id("Fixes #123 (BUG-99 regression)") == "BUG-99"

    def test_trailer_reference(self) -> None:
        from little_loops.session_store import _infer_issue_id

        assert _infer_issue_id("feat: add thing\n\nIssue: FEAT-777") == "FEAT-777"

    def test_bare_typed_token(self) -> None:
        from little_loops.session_store import _infer_issue_id

        assert _infer_issue_id("enh(store): ENH-2458 add commit_events") == "ENH-2458"

    def test_branch_convention(self) -> None:
        from little_loops.session_store import _infer_issue_id

        assert _infer_issue_id("misc cleanup", branch="feat/ENH-2458-commit-events") == "ENH-2458"

    def test_no_reference_returns_none(self) -> None:
        from little_loops.session_store import _infer_issue_id

        assert _infer_issue_id("chore: tidy imports", branch="main") is None


class TestRecordCommitEvent:
    """ENH-2458: record_commit_event() DB write round-trip."""

    def test_roundtrip(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_commit_event

        db = tmp_path / "history.db"
        inserted = record_commit_event(
            db,
            "abc123def456",
            "enh(store): add commit_events (ENH-2458)",
            author="Test Author",
            branch="feat/ENH-2458-commits",
            files=["scripts/little_loops/session_store.py"],
            parent_sha="000111",
        )
        assert inserted
        rows = recent(db, kind="commit")
        assert len(rows) == 1
        assert rows[0]["commit_sha"] == "abc123def456"
        assert rows[0]["issue_id"] == "ENH-2458"
        assert rows[0]["branch"] == "feat/ENH-2458-commits"
        assert json.loads(rows[0]["files_json"]) == ["scripts/little_loops/session_store.py"]

    def test_dedupe_on_sha(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_commit_event

        db = tmp_path / "history.db"
        assert record_commit_event(db, "dupsha", "first")
        assert not record_commit_event(db, "dupsha", "second attempt")
        rows = recent(db, kind="commit")
        assert len(rows) == 1
        assert rows[0]["message"] == "first"

    def test_fts_searchable_by_message_fragment(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_commit_event

        db = tmp_path / "history.db"
        record_commit_event(db, "ftssha", "fix flaky teleporter alignment")
        results = search(db, query="teleporter")
        assert any(r["kind"] == "commit" for r in results)

    def test_explicit_issue_id_not_overridden(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_commit_event

        db = tmp_path / "history.db"
        record_commit_event(db, "explsha", "mentions BUG-1 in passing", issue_id="ENH-42")
        rows = recent(db, kind="commit")
        assert rows[0]["issue_id"] == "ENH-42"


def _bootstrap_schema_at(db: Path, version: int) -> None:
    """Bootstrap a database at an exact historical schema *version*.

    Applies migrations 0..version-1 verbatim from ``_MIGRATIONS`` and stamps
    the meta row, mirroring the TestSchemaV14 pattern so upgrade tests always
    exercise the real historical DDL.
    """
    from little_loops.session_store import _MIGRATIONS, _split_sql_statements

    conn = sqlite3.connect(str(db))
    try:
        for script in _MIGRATIONS[:version]:
            for stmt in _split_sql_statements(script):
                conn.execute(stmt)
        conn.execute(
            "INSERT OR IGNORE INTO meta(key, value) VALUES('schema_version', ?)",
            (str(version),),
        )
        conn.commit()
    finally:
        conn.close()


class TestRecordTestRunEvent:
    """ENH-2459: record_test_run_event() DB write round-trip."""

    def test_roundtrip(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_test_run_event

        db = tmp_path / "history.db"
        record_test_run_event(
            db,
            ts="2026-07-01T12:00:00Z",
            ended_at="2026-07-01T12:00:31Z",
            total=10,
            passed=8,
            failed=1,
            errored=1,
            skipped=0,
            duration_s=31.2,
            failing_names=["tests/test_x.py::test_flaky"],
            env_label="local",
            head_sha="deadbeef",
            branch="main",
            command="python -m pytest scripts/tests/",
        )
        rows = recent(db, kind="test_run")
        assert len(rows) == 1
        row = rows[0]
        assert row["total"] == 10
        assert row["passed"] == 8
        assert row["failed"] == 1
        assert row["errored"] == 1
        assert json.loads(row["failing_names_json"]) == ["tests/test_x.py::test_flaky"]
        assert row["env_label"] == "local"
        assert row["head_sha"] == "deadbeef"

    def test_failing_names_fts_searchable(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_test_run_event

        db = tmp_path / "history.db"
        record_test_run_event(
            db,
            ts="2026-07-01T12:00:00Z",
            total=1,
            failed=1,
            failing_names=["tests/test_teleporter.py::test_alignment"],
        )
        results = search(db, query="teleporter")
        assert any(r["kind"] == "test_run" for r in results)

    def test_multiple_runs_are_distinct_rows(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_test_run_event

        db = tmp_path / "history.db"
        record_test_run_event(db, ts="2026-07-01T12:00:00Z", total=1, passed=1)
        record_test_run_event(db, ts="2026-07-01T12:05:00Z", total=1, passed=1)
        rows = recent(db, kind="test_run")
        assert len(rows) == 2
        assert rows[0]["ts"] > rows[1]["ts"]

    def test_v14_db_upgrades_gains_test_run_events(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        _bootstrap_schema_at(db, 14)
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            names = {
                r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
        finally:
            conn.close()
        assert "test_run_events" in names
        assert "commit_events" in names


class TestOrchestrationRuns:
    """ENH-2492: orchestration_runs schema, UPSERT, and FTS contract."""

    @staticmethod
    def _recorder():
        from little_loops import session_store

        recorder = getattr(session_store, "record_orchestration_run", None)
        assert callable(recorder), "record_orchestration_run must be public"
        return recorder

    def test_v21_db_upgrades_gains_orchestration_runs(self, tmp_path: Path) -> None:
        assert SCHEMA_VERSION == 45
        db = tmp_path / "history.db"
        _bootstrap_schema_at(db, 21)
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            names = {
                r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            indexes = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='index' AND tbl_name='orchestration_runs'"
                )
            }
        finally:
            conn.close()
        assert "orchestration_runs" in names
        assert {
            "idx_orchestration_runs_driver",
            "idx_orchestration_runs_issue_id",
            "idx_orchestration_runs_status",
        } <= indexes

    def test_roundtrip(self, tmp_path: Path) -> None:
        record_orchestration_run = self._recorder()
        db = tmp_path / "history.db"
        record_orchestration_run(
            db,
            run_id="batch-1",
            driver="ll-sprint",
            issue_id="ENH-2492",
            status="failed",
            failure_reason="teleporterfailure",
            duration_s=12.5,
            wave="Wave 2/3",
            pr_url="https://example.test/pr/42",
            started_at="2026-07-17T10:00:00Z",
            ended_at="2026-07-17T10:00:13Z",
            head_sha="abc123",
            branch="feature/ENH-2492",
        )

        rows = recent(db, kind="orchestration_run")
        assert len(rows) == 1
        row = rows[0]
        assert row["run_id"] == "batch-1"
        assert row["driver"] == "ll-sprint"
        assert row["issue_id"] == "ENH-2492"
        assert row["status"] == "failed"
        assert row["failure_reason"] == "teleporterfailure"
        assert row["duration_s"] == 12.5
        assert row["wave"] == "Wave 2/3"
        assert row["pr_url"] == "https://example.test/pr/42"

    def test_upsert_replaces_outcome_and_fts_row(self, tmp_path: Path) -> None:
        record_orchestration_run = self._recorder()
        db = tmp_path / "history.db"
        common = {
            "run_id": "batch-retry",
            "driver": "ll-sprint",
            "issue_id": "BUG-17",
            "wave": "Wave 1/1",
        }
        record_orchestration_run(
            db,
            **common,
            status="failed",
            failure_reason="teleporterfailure",
            duration_s=4.0,
        )
        record_orchestration_run(
            db,
            **common,
            status="completed",
            failure_reason=None,
            duration_s=2.0,
        )

        rows = recent(db, kind="orchestration_run")
        assert len(rows) == 1
        assert rows[0]["status"] == "completed"
        assert rows[0]["failure_reason"] is None
        assert rows[0]["duration_s"] == 2.0
        stale = search(db, query="teleporterfailure")
        assert not any(row["kind"] == "orchestration_run" for row in stale)
        completed = [
            row for row in search(db, query="completed") if row["kind"] == "orchestration_run"
        ]
        assert len(completed) == 1

        conn = connect(db)
        try:
            indexed = conn.execute(
                "SELECT COUNT(*) FROM search_index WHERE kind='orchestration_run'"
            ).fetchone()[0]
        finally:
            conn.close()
        assert indexed == 1

    def test_identical_write_is_idempotent(self, tmp_path: Path) -> None:
        record_orchestration_run = self._recorder()
        db = tmp_path / "history.db"
        kwargs = {
            "run_id": "batch-same",
            "driver": "ll-auto",
            "issue_id": "ENH-1",
            "status": "completed",
            "duration_s": 1.0,
        }
        record_orchestration_run(db, **kwargs)
        record_orchestration_run(db, **kwargs)

        conn = connect(db)
        try:
            table_rows = conn.execute("SELECT COUNT(*) FROM orchestration_runs").fetchone()[0]
            fts_rows = conn.execute(
                "SELECT COUNT(*) FROM search_index WHERE kind='orchestration_run'"
            ).fetchone()[0]
        finally:
            conn.close()
        assert table_rows == 1
        assert fts_rows == 1


class TestPrepatchEvidence:
    """ENH-2997: prepatch_evidence table, writer, and reader round trip."""

    def test_v39_db_upgrades_gains_prepatch_evidence(self, tmp_path: Path) -> None:
        assert SCHEMA_VERSION == 45
        db = tmp_path / "history.db"
        _bootstrap_schema_at(db, 39)
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            names = {
                r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            indexes = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='index' AND tbl_name='prepatch_evidence'"
                )
            }
        finally:
            conn.close()
        assert "prepatch_evidence" in names
        assert "idx_prepatch_evidence_issue_id" in indexes

    def test_record_and_read_roundtrip(self, tmp_path: Path) -> None:
        from little_loops.history_reader import read_prepatch_evidence
        from little_loops.session_store import record_prepatch_evidence

        db = tmp_path / "history.db"
        evidence = {
            "base_ref": "deadbeef",
            "base_source": "merge-base",
            "base_dirty": None,
            "outcomes": [],
            "verdict": "flagged",
            "skipped_reason": None,
            "worktree_path": None,
        }
        ok = record_prepatch_evidence(
            db, issue_id="ENH-2997", evidence=evidence, run_id="run-1", state="verify"
        )
        assert ok is True

        result = read_prepatch_evidence("ENH-2997", db=db)
        assert result == evidence

    def test_read_returns_none_for_missing_db_or_unknown_issue(self, tmp_path: Path) -> None:
        from little_loops.history_reader import read_prepatch_evidence

        assert read_prepatch_evidence("ENH-9999", db=tmp_path / "missing.db") is None

        db = tmp_path / "history.db"
        ensure_db(db)
        assert read_prepatch_evidence("ENH-9999", db=db) is None

    def test_two_rows_never_upserted_reader_takes_most_recent(self, tmp_path: Path) -> None:
        from little_loops.history_reader import read_prepatch_evidence
        from little_loops.session_store import record_prepatch_evidence

        db = tmp_path / "history.db"
        record_prepatch_evidence(
            db, issue_id="ENH-2997", evidence={"verdict": "clean"}, state="step1"
        )
        record_prepatch_evidence(
            db, issue_id="ENH-2997", evidence={"verdict": "flagged"}, state="step2"
        )

        conn = connect(db)
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM prepatch_evidence WHERE issue_id = ?", ("ENH-2997",)
            ).fetchone()[0]
        finally:
            conn.close()
        assert count == 2
        assert read_prepatch_evidence("ENH-2997", db=db) == {"verdict": "flagged"}

    def test_empty_issue_id_returns_false(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_prepatch_evidence

        db = tmp_path / "history.db"
        assert record_prepatch_evidence(db, issue_id="", evidence={}) is False


class TestOrchestrationRunBaseStamp:
    """ENH-2866: dequeue-time base-SHA stamp written by an early ``running`` upsert."""

    @staticmethod
    def _recorder():
        from little_loops import session_store

        recorder = getattr(session_store, "record_orchestration_run", None)
        assert callable(recorder), "record_orchestration_run must be public"
        return recorder

    @staticmethod
    def _row(db: Path, run_id: str, issue_id: str) -> sqlite3.Row:
        conn = connect(db)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT * FROM orchestration_runs WHERE run_id = ? AND issue_id = ?",
                (run_id, issue_id),
            ).fetchone()
        finally:
            conn.close()
        assert row is not None
        return row

    def test_early_upsert_persists_stamp_and_leaves_ended_at_null(self, tmp_path: Path) -> None:
        """An in-flight row records the stamp without claiming an end time."""
        record_orchestration_run = self._recorder()
        db = tmp_path / "history.db"
        record_orchestration_run(
            db,
            run_id="run-1",
            driver="ll-auto",
            issue_id="ENH-2866",
            status="running",
            started_at="2026-08-01T10:00:00Z",
            base_sha="deadbeef",
            base_dirty=False,
        )
        row = self._row(db, "run-1", "ENH-2866")
        assert row["base_sha"] == "deadbeef"
        assert row["base_dirty"] == 0
        assert row["started_at"] == "2026-08-01T10:00:00Z"
        assert row["ended_at"] is None

    def test_terminal_upsert_preserves_stamp_and_started_at_in_one_row(
        self, tmp_path: Path
    ) -> None:
        """The terminal write replaces the outcome but keeps the dequeue-time values."""
        record_orchestration_run = self._recorder()
        db = tmp_path / "history.db"
        record_orchestration_run(
            db,
            run_id="run-2",
            driver="ll-auto",
            issue_id="ENH-2866",
            status="running",
            started_at="2026-08-01T10:00:00Z",
            base_sha="cafe1234",
            base_dirty=True,
        )
        # The terminal call mirrors the three real call sites: no started_at,
        # no base_sha, no ended_at.
        record_orchestration_run(
            db,
            run_id="run-2",
            driver="ll-auto",
            issue_id="ENH-2866",
            status="completed",
            duration_s=9.5,
            head_sha="ffff0000",
            branch="main",
        )
        row = self._row(db, "run-2", "ENH-2866")
        assert row["status"] == "completed"
        assert row["duration_s"] == 9.5
        assert row["head_sha"] == "ffff0000"
        assert row["branch"] == "main"
        assert row["base_sha"] == "cafe1234", "COALESCE must keep the dequeue-time stamp"
        assert row["base_dirty"] == 1
        assert row["started_at"] == "2026-08-01T10:00:00Z", (
            "the terminal upsert must not null the dequeue timestamp — "
            "history_reader windows key on COALESCE(ended_at, started_at)"
        )
        assert row["ended_at"] is not None

        conn = connect(db)
        try:
            count = conn.execute("SELECT COUNT(*) FROM orchestration_runs").fetchone()[0]
        finally:
            conn.close()
        assert count == 1, "early + terminal writes must produce one row, not two"

    def test_abandoned_in_flight_row_stays_in_windowed_queries(self, tmp_path: Path) -> None:
        """A crashed run keeps started_at, so it is not lost to COALESCE windows."""
        from little_loops.history_reader import recent_orchestration_runs

        record_orchestration_run = self._recorder()
        db = tmp_path / "history.db"
        record_orchestration_run(
            db,
            run_id="run-crash",
            driver="ll-parallel",
            issue_id="BUG-99",
            status="running",
            started_at="2026-08-01T10:00:00Z",
            base_sha="abc",
        )
        row = self._row(db, "run-crash", "BUG-99")
        assert row["ended_at"] is None
        assert row["ended_at"] != row["started_at"]

        found = recent_orchestration_runs(issue_id="BUG-99", since="2026-07-01T00:00:00Z", db=db)
        assert [r.status for r in found] == ["running"]

    def test_retry_without_stamp_does_not_clobber_recorded_stamp(self, tmp_path: Path) -> None:
        """A later upsert passing base_sha=None leaves the recorded stamp intact."""
        record_orchestration_run = self._recorder()
        db = tmp_path / "history.db"
        common = {"run_id": "run-3", "driver": "ll-sprint", "issue_id": "BUG-1"}
        record_orchestration_run(db, **common, status="running", base_sha="1234abc", base_dirty=0)
        record_orchestration_run(db, **common, status="failed", failure_reason="boom")
        record_orchestration_run(db, **common, status="completed")
        row = self._row(db, "run-3", "BUG-1")
        assert row["base_sha"] == "1234abc"
        assert row["base_dirty"] == 0
        assert row["status"] == "completed"

    def test_empty_base_sha_is_stored_as_null(self, tmp_path: Path) -> None:
        """A failed ``git rev-parse`` ("" from _get_main_head_sha) must not become ''."""
        record_orchestration_run = self._recorder()
        db = tmp_path / "history.db"
        record_orchestration_run(
            db,
            run_id="run-4",
            driver="ll-parallel",
            issue_id="BUG-2",
            status="running",
            base_sha="",
        )
        row = self._row(db, "run-4", "BUG-2")
        assert row["base_sha"] is None

    def test_unstamped_write_leaves_columns_null(self, tmp_path: Path) -> None:
        """An orchestrator that never stamps keeps working; NULL means unstamped."""
        record_orchestration_run = self._recorder()
        db = tmp_path / "history.db"
        record_orchestration_run(
            db, run_id="run-5", driver="ll-auto", issue_id="BUG-3", status="completed"
        )
        row = self._row(db, "run-5", "BUG-3")
        assert row["base_sha"] is None
        assert row["base_dirty"] is None
        assert row["ended_at"] is not None, "a terminal write still defaults ended_at"


class TestLoopRuns:
    """loop_runs summary rows (ENH-2463)."""

    @staticmethod
    def _recorder():
        from little_loops import session_store

        recorder = getattr(session_store, "record_loop_run_summary", None)
        assert callable(recorder), "record_loop_run_summary must be public"
        return recorder

    @staticmethod
    def _diagnostics_updater():
        from little_loops import session_store

        updater = getattr(session_store, "update_loop_run_diagnostics", None)
        assert callable(updater), "update_loop_run_diagnostics must be public"
        return updater

    def test_v22_db_upgrades_gains_loop_runs(self, tmp_path: Path) -> None:
        assert SCHEMA_VERSION == 45
        db = tmp_path / "history.db"
        _bootstrap_schema_at(db, 22)
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            names = {
                r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            indexes = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='loop_runs'"
                )
            }
        finally:
            conn.close()
        assert "loop_runs" in names
        assert {
            "idx_loop_runs_loop_name",
            "idx_loop_runs_terminated_by",
            "idx_loop_runs_evaluator_score",
        } <= indexes

    def test_roundtrip(self, tmp_path: Path) -> None:
        record_loop_run_summary = self._recorder()
        db = tmp_path / "history.db"
        record_loop_run_summary(
            db,
            run_id="20260717T101530-rn-implement",
            loop_name="rn-implement",
            started_at="2026-07-17T10:15:30Z",
            ended_at="2026-07-17T10:20:00Z",
            final_state="done",
            iterations=3,
            terminated_by="terminal",
            head_sha="abc123",
            branch="feature/ENH-2463",
        )

        rows = recent(db, kind="loop_run")
        assert len(rows) == 1
        row = rows[0]
        assert row["run_id"] == "20260717T101530-rn-implement"
        assert row["loop_name"] == "rn-implement"
        assert row["final_state"] == "done"
        assert row["iterations"] == 3
        assert row["terminated_by"] == "terminal"
        assert row["evaluator_score"] is None
        assert row["diagnostics_path"] is None

    def test_error_termination(self, tmp_path: Path) -> None:
        record_loop_run_summary = self._recorder()
        db = tmp_path / "history.db"
        record_loop_run_summary(
            db,
            run_id="20260717T101530-rn-refine",
            loop_name="rn-refine",
            terminated_by="error",
            error="boom",
        )
        rows = recent(db, kind="loop_run")
        assert rows[0]["terminated_by"] == "error"
        assert rows[0]["error"] == "boom"

    def test_duplicate_run_id_is_idempotent(self, tmp_path: Path) -> None:
        record_loop_run_summary = self._recorder()
        db = tmp_path / "history.db"
        kwargs = {
            "run_id": "20260717T101530-rn-implement",
            "loop_name": "rn-implement",
            "terminated_by": "terminal",
        }
        record_loop_run_summary(db, **kwargs)
        record_loop_run_summary(db, **kwargs)

        conn = connect(db)
        try:
            table_rows = conn.execute("SELECT COUNT(*) FROM loop_runs").fetchone()[0]
            fts_rows = conn.execute(
                "SELECT COUNT(*) FROM search_index WHERE kind='loop_run'"
            ).fetchone()[0]
        finally:
            conn.close()
        assert table_rows == 1
        assert fts_rows == 1

    def test_missing_identity_fields_returns_false(self, tmp_path: Path) -> None:
        record_loop_run_summary = self._recorder()
        db = tmp_path / "history.db"
        assert record_loop_run_summary(db, run_id="", loop_name="rn-implement") is False
        assert record_loop_run_summary(db, run_id="run-1", loop_name="") is False

    def test_update_loop_run_diagnostics_links_artifact(self, tmp_path: Path) -> None:
        record_loop_run_summary = self._recorder()
        update_loop_run_diagnostics = self._diagnostics_updater()
        db = tmp_path / "history.db"
        record_loop_run_summary(
            db,
            run_id="20260717T101530-rn-implement",
            loop_name="rn-implement",
            terminated_by="terminal",
        )
        result = update_loop_run_diagnostics(
            db, "20260717T101530-rn-implement", ".loops/diagnostics/rn-implement-20260717.md"
        )
        assert result is True

        rows = recent(db, kind="loop_run")
        assert rows[0]["diagnostics_path"] == ".loops/diagnostics/rn-implement-20260717.md"
        # other fields untouched by the diagnostics-only update
        assert rows[0]["terminated_by"] == "terminal"

    def test_update_loop_run_diagnostics_missing_run_id_returns_false(self, tmp_path: Path) -> None:
        update_loop_run_diagnostics = self._diagnostics_updater()
        db = tmp_path / "history.db"
        ensure_db(db)
        assert update_loop_run_diagnostics(db, "no-such-run", "path.md") is False


class TestRecordLearningTestEvent:
    """ENH-2466: record_learning_test_event() DB write round-trip."""

    @staticmethod
    def _write_registry_file(base: Path, target: str = "anthropic") -> Path:
        from little_loops.issue_parser import slugify
        from little_loops.learning_tests import Assertion, LearnTestRecord, write_record

        record = LearnTestRecord(
            target=target,
            date="2026-07-19",
            status="proven",
            assertions=[Assertion(claim="streaming works", result="pass")],
            raw_output_path=f".ll/learning-tests/raw/{slugify(target)}.txt",
        )
        return write_record(record, base_dir=base)

    def test_roundtrip(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_learning_test_event

        registry_dir = tmp_path / "registry"
        registry_dir.mkdir()
        path = self._write_registry_file(registry_dir)

        db = tmp_path / "history.db"
        assert record_learning_test_event(db, "anthropic", str(path))
        rows = recent(db, kind="learning_test")
        assert len(rows) == 1
        assert rows[0]["record_id"] == "anthropic"
        assert rows[0]["status"] == "proven"
        assert json.loads(rows[0]["assertions_json"]) == [
            {"claim": "streaming works", "result": "pass"}
        ]

    def test_dedupe_on_record_id_upserts(self, tmp_path: Path) -> None:
        from little_loops.issue_parser import slugify
        from little_loops.learning_tests import Assertion, LearnTestRecord, write_record
        from little_loops.session_store import record_learning_test_event

        registry_dir = tmp_path / "registry"
        registry_dir.mkdir()
        path = self._write_registry_file(registry_dir)
        db = tmp_path / "history.db"
        assert record_learning_test_event(db, "anthropic", str(path))

        stale_record = LearnTestRecord(
            target="anthropic",
            date="2026-07-20",
            status="stale",
            assertions=[Assertion(claim="streaming works", result="fail")],
            raw_output_path=f".ll/learning-tests/raw/{slugify('anthropic')}.txt",
        )
        write_record(stale_record, base_dir=registry_dir)
        assert record_learning_test_event(db, "anthropic", str(path))

        rows = recent(db, kind="learning_test")
        assert len(rows) == 1
        assert rows[0]["status"] == "stale"

    def test_fts_searchable_by_claim_fragment(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_learning_test_event

        registry_dir = tmp_path / "registry"
        registry_dir.mkdir()
        path = self._write_registry_file(registry_dir)
        db = tmp_path / "history.db"
        record_learning_test_event(db, "anthropic", str(path))
        results = search(db, query="streaming")
        assert any(r["kind"] == "learning_test" for r in results)

    def test_missing_file_is_noop(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_learning_test_event

        db = tmp_path / "history.db"
        assert not record_learning_test_event(db, "anthropic", str(tmp_path / "no-such.md"))
        assert recent(db, kind="learning_test") == []

    def test_v25_db_upgrades_gains_learning_test_events(self, tmp_path: Path) -> None:
        assert SCHEMA_VERSION == 45
        db = tmp_path / "history.db"
        _bootstrap_schema_at(db, 25)
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            names = {
                r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
        finally:
            conn.close()
        assert "learning_test_events" in names


class TestRecordUsageEvent:
    """ENH-2724: live per-invocation usage_events writer."""

    def test_inserts_row_with_run_id_and_state(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_usage_event

        db = tmp_path / "history.db"
        ensure_db(db)
        record_usage_event(
            db,
            run_id="20260721190000-test-loop",
            ts="2026-07-21T19:00:00Z",
            state="check",
            model="claude-sonnet-4-6",
            input_tokens=100,
            output_tokens=50,
            cache_read_tokens=10,
            cache_creation_tokens=5,
        )
        conn = connect(db)
        try:
            row = conn.execute(
                "SELECT run_id, state, model, input_tokens, output_tokens, "
                "cache_read_input_tokens, cache_creation_input_tokens, cost_usd "
                "FROM usage_events WHERE run_id = ?",
                ("20260721190000-test-loop",),
            ).fetchone()
        finally:
            conn.close()
        assert row is not None
        assert row[0] == "20260721190000-test-loop"
        assert row[1] == "check"
        assert row[2] == "claude-sonnet-4-6"
        assert row[3] == 100
        assert row[4] == 50
        assert row[5] == 10
        assert row[6] == 5
        assert row[7] is not None  # cost_usd computed

    def test_state_none_is_stored_as_null(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_usage_event

        db = tmp_path / "history.db"
        ensure_db(db)
        record_usage_event(
            db,
            run_id="20260721190000-test-loop",
            ts="2026-07-21T19:00:00Z",
            state=None,
            model="claude-sonnet-5",
            input_tokens=1,
            output_tokens=1,
            cache_read_tokens=0,
            cache_creation_tokens=0,
        )
        conn = connect(db)
        try:
            row = conn.execute(
                "SELECT state FROM usage_events WHERE run_id = ?",
                ("20260721190000-test-loop",),
            ).fetchone()
        finally:
            conn.close()
        assert row is not None
        assert row[0] is None

    def test_concurrent_writers_do_not_cross_attribute_or_lose_rows(self, tmp_path: Path) -> None:
        """Regression coverage carried over from the ENH-2712 spike: concurrent
        ll-parallel/ll-sprint writers must not cross-attribute run_id or drop rows."""
        import threading

        from little_loops.session_store import record_usage_event

        db = tmp_path / "history.db"
        ensure_db(db)

        run_ids = [f"run-{i}" for i in range(8)]

        def _write(run_id: str) -> None:
            record_usage_event(
                db,
                run_id=run_id,
                ts="2026-07-21T19:00:00Z",
                state="check",
                model="claude-sonnet-4-6",
                input_tokens=1,
                output_tokens=1,
                cache_read_tokens=0,
                cache_creation_tokens=0,
            )

        threads = [threading.Thread(target=_write, args=(rid,)) for rid in run_ids]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        conn = connect(db)
        try:
            rows = conn.execute(
                "SELECT run_id FROM usage_events WHERE run_id LIKE 'run-%'"
            ).fetchall()
        finally:
            conn.close()
        assert sorted(r[0] for r in rows) == sorted(run_ids)


class TestRecordSessionLifecycleEvent:
    """ENH-2495: record_session_lifecycle_event() DB write round-trip."""

    def test_roundtrip(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_session_lifecycle_event

        db = tmp_path / "history.db"
        assert record_session_lifecycle_event(
            db,
            session_id="s1",
            event="handoff_needed",
            detail={"threshold_pct": 82},
        )
        rows = recent(db, kind="session_lifecycle")
        assert len(rows) == 1
        assert rows[0]["session_id"] == "s1"
        assert rows[0]["event"] == "handoff_needed"
        assert json.loads(rows[0]["detail"]) == {"threshold_pct": 82}

    def test_event_discriminator_filters(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_session_lifecycle_event

        db = tmp_path / "history.db"
        record_session_lifecycle_event(db, session_id="s1", event="handoff_needed")
        record_session_lifecycle_event(db, session_id="s1", event="stale_ref_sweep")
        rows = recent(db, kind="session_lifecycle")
        assert {r["event"] for r in rows} == {"handoff_needed", "stale_ref_sweep"}

    def test_fts_searchable_by_event(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_session_lifecycle_event

        db = tmp_path / "history.db"
        record_session_lifecycle_event(db, session_id="s1", event="compaction")
        results = search(db, query="compaction")
        assert any(r["kind"] == "session_lifecycle" for r in results)

    def test_graceful_when_store_unwritable(self, tmp_path: Path, monkeypatch) -> None:
        import little_loops.session_store as session_store

        def boom(*_args, **_kwargs):  # type: ignore[no-untyped-def]
            raise sqlite3.OperationalError("database is locked")

        monkeypatch.setattr(session_store, "connect", boom)

        db = tmp_path / "history.db"
        assert not session_store.record_session_lifecycle_event(
            db, session_id="s1", event="handoff_needed"
        )


class TestRecordHookEvent:
    """ENH-2506: record_hook_event() single-row INSERT."""

    def test_inserts_row_with_all_columns(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_hook_event

        db = tmp_path / "history.db"
        record_hook_event(
            db,
            session_id="sess-1",
            event_name="PostToolUse",
            matcher="Write|Edit",
            script="little_loops.hooks.post_tool_use",
            exit_code=0,
            duration_ms=12,
            stderr_preview="warn: x",
            head_sha="abc123",
            branch="main",
        )
        rows = recent(db, kind="hook_event")
        assert len(rows) == 1
        assert rows[0]["event_name"] == "PostToolUse"
        assert rows[0]["matcher"] == "Write|Edit"
        assert rows[0]["script"] == "little_loops.hooks.post_tool_use"
        assert rows[0]["exit_code"] == 0
        assert rows[0]["duration_ms"] == 12
        assert rows[0]["stderr_preview"] == "warn: x"

    def test_multi_row_ordering(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_hook_event

        db = tmp_path / "history.db"
        for i in range(3):
            record_hook_event(
                db,
                session_id="sess-1",
                event_name="PostToolUse",
                matcher=None,
                script=None,
                exit_code=0,
                duration_ms=i,
            )
        rows = recent(db, kind="hook_event", limit=10)
        assert [r["duration_ms"] for r in rows] == [2, 1, 0]

    def test_kwarg_only_signature(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_hook_event

        db = tmp_path / "history.db"
        with pytest.raises(TypeError):
            record_hook_event(db, "sess-1", "PostToolUse", None, None, 0, 1)  # type: ignore[misc]

    def test_stderr_preview_truncated_to_512(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_hook_event

        db = tmp_path / "history.db"
        record_hook_event(
            db,
            session_id=None,
            event_name="PostToolUse",
            matcher=None,
            script=None,
            exit_code=1,
            duration_ms=1,
            stderr_preview="x" * 1000,
        )
        rows = recent(db, kind="hook_event")
        assert len(rows[0]["stderr_preview"]) == 512

    def test_fts_indexed(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_hook_event

        db = tmp_path / "history.db"
        record_hook_event(
            db,
            session_id="sess-1",
            event_name="PreCompact",
            matcher=None,
            script=None,
            exit_code=0,
            duration_ms=1,
        )
        results = search(db, query="PreCompact")
        assert any(r["kind"] == "hook_event" for r in results)

    def test_best_effort_on_unopenable_db(self, tmp_path: Path) -> None:
        """A db path that cannot be opened must not raise."""
        from little_loops.session_store import record_hook_event

        # tmp_path is a directory — sqlite cannot open it as a database file.
        record_hook_event(
            tmp_path,
            session_id=None,
            event_name="PostToolUse",
            matcher=None,
            script=None,
            exit_code=0,
            duration_ms=1,
        )


class TestHookEventContext:
    """ENH-2506: hook_event_context() insert-on-exit round-trip."""

    def test_success_path_records_exit_code_zero(self, tmp_path: Path) -> None:
        from little_loops.session_store import hook_event_context

        db = tmp_path / "history.db"
        with hook_event_context(db, session_id="s1", event_name="PostToolUse", matcher="Write"):
            pass
        rows = recent(db, kind="hook_event")
        assert len(rows) == 1
        assert rows[0]["exit_code"] == 0
        assert rows[0]["duration_ms"] is not None
        assert rows[0]["duration_ms"] >= 0

    def test_raise_path_records_exit_code_one_and_propagates(self, tmp_path: Path) -> None:
        from little_loops.session_store import hook_event_context

        db = tmp_path / "history.db"
        with pytest.raises(ValueError):
            with hook_event_context(db, session_id="s1", event_name="PreCompact"):
                raise ValueError("boom")
        rows = recent(db, kind="hook_event")
        assert rows[0]["exit_code"] == 1

    def test_host_provided_exit_code_wins(self, tmp_path: Path) -> None:
        from little_loops.session_store import hook_event_context

        db = tmp_path / "history.db"
        with hook_event_context(db, session_id="s1", event_name="Stop") as completion:
            completion.exit_code = 7
        rows = recent(db, kind="hook_event")
        assert rows[0]["exit_code"] == 7

    def test_custom_matcher_script_propagation(self, tmp_path: Path) -> None:
        from little_loops.session_store import hook_event_context

        db = tmp_path / "history.db"
        with hook_event_context(
            db,
            session_id="s1",
            event_name="PostToolUse",
            matcher="Edit|Write|MultiEdit",
            script="little_loops.hooks.edit_batch_nudge",
        ):
            pass
        rows = recent(db, kind="hook_event")
        assert rows[0]["matcher"] == "Edit|Write|MultiEdit"
        assert rows[0]["script"] == "little_loops.hooks.edit_batch_nudge"

    def test_completion_stderr_preview_propagation(self, tmp_path: Path) -> None:
        from little_loops.session_store import hook_event_context

        db = tmp_path / "history.db"
        with hook_event_context(db, session_id="s1", event_name="PostToolUse") as completion:
            completion.stderr_preview = "some warning"
        rows = recent(db, kind="hook_event")
        assert rows[0]["stderr_preview"] == "some warning"

    def test_best_effort_on_unopenable_db(self, tmp_path: Path) -> None:
        """A db path that cannot be opened must not prevent the body from running."""
        from little_loops.session_store import hook_event_context

        ran = False
        with hook_event_context(tmp_path, session_id=None, event_name="PostToolUse"):
            ran = True
        assert ran


class TestRecordHarnessEvent:
    """ENH-2739: record_harness_event() single-row INSERT."""

    def test_inserts_row_with_all_columns(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_harness_event

        db = tmp_path / "history.db"
        record_harness_event(
            db,
            ts="2026-07-22T00:00:00Z",
            runner="cmd",
            target="scripts/tests/test_foo.py",
            exit_code=0,
            semantic_verdict="pass",
            semantic_passed=True,
            timed_out=False,
            duration_ms=1234,
            head_sha="abc123",
            branch="main",
            parent_id=None,
            semantic_prompt="does the output match?",
            semantic_confidence=0.92,
            semantic_reason="output matched expected format",
            semantic_evidence="line 3: OK",
            semantic_model="claude-sonnet-5",
            target_content_hash="0123456789abcdef",
            target_path="/abs/path/to/skill.md",
            dirty=1,
        )
        rows = recent(db, kind="harness")
        assert len(rows) == 1
        row = rows[0]
        assert row["runner"] == "cmd"
        assert row["target"] == "scripts/tests/test_foo.py"
        assert row["exit_code"] == 0
        assert row["semantic_verdict"] == "pass"
        assert row["semantic_passed"] == 1
        assert row["timed_out"] == 0
        assert row["duration_ms"] == 1234
        assert row["head_sha"] == "abc123"
        assert row["branch"] == "main"
        assert row["semantic_prompt"] == "does the output match?"
        assert row["semantic_confidence"] == 0.92
        assert row["semantic_reason"] == "output matched expected format"
        assert row["semantic_evidence"] == "line 3: OK"
        assert row["semantic_model"] == "claude-sonnet-5"
        assert row["target_content_hash"] == "0123456789abcdef"
        assert row["target_path"] == "/abs/path/to/skill.md"
        assert row["dirty"] == 1

    def test_parent_id_round_trips_for_dsl_subtasks(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_harness_event

        db = tmp_path / "history.db"
        record_harness_event(db, ts="2026-07-22T00:00:00Z", runner="dsl", target="parent-run")
        conn = connect(db)
        try:
            parent_id = conn.execute("SELECT id FROM harness_events").fetchone()[0]
        finally:
            conn.close()
        record_harness_event(
            db,
            ts="2026-07-22T00:00:01Z",
            runner="dsl",
            target="task-1",
            parent_id=parent_id,
        )
        rows = recent(db, kind="harness", limit=10)
        child = next(r for r in rows if r["target"] == "task-1")
        assert child["parent_id"] == parent_id

    def test_kwarg_only_signature(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_harness_event

        db = tmp_path / "history.db"
        with pytest.raises(TypeError):
            record_harness_event(db, "2026-07-22T00:00:00Z", "cmd")  # type: ignore[misc]

    def test_raises_on_unopenable_db(self, tmp_path: Path) -> None:
        """Unlike record_hook_event, this recorder raises on failure (per issue contract)."""
        from little_loops.session_store import record_harness_event

        # tmp_path is a directory — sqlite cannot open it as a database file.
        with pytest.raises(sqlite3.Error):
            record_harness_event(tmp_path, ts="2026-07-22T00:00:00Z", runner="cmd")

    def test_fts_indexed(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_harness_event

        db = tmp_path / "history.db"
        record_harness_event(
            db,
            ts="2026-07-22T00:00:00Z",
            runner="mcp",
            target="unique-search-target-xyz",
            exit_code=1,
        )
        results = search(db, query="unique-search-target-xyz")
        assert any(r["kind"] == "harness" for r in results)


class TestRecordPromptOptEvent:
    """ENH-2498: record_prompt_opt_event() single-row INSERT."""

    def test_inserts_offered_row(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_prompt_opt_event

        db = tmp_path / "history.db"
        record_prompt_opt_event(
            db,
            ts="2026-07-23T00:00:00Z",
            session_id="sess-1",
            mode="thorough",
            offered=True,
            raw_len=42,
        )
        rows = recent(db, kind="prompt_opt")
        assert len(rows) == 1
        row = rows[0]
        assert row["session_id"] == "sess-1"
        assert row["mode"] == "thorough"
        assert row["offered"] == 1
        assert row["bypass_reason"] is None
        assert row["raw_len"] == 42
        assert row["optimized_text"] is None
        assert row["accepted"] is None

    def test_inserts_bypass_row(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_prompt_opt_event

        db = tmp_path / "history.db"
        record_prompt_opt_event(
            db,
            ts="2026-07-23T00:00:00Z",
            session_id="sess-2",
            mode="quick",
            offered=False,
            bypass_reason="short",
            raw_len=5,
        )
        rows = recent(db, kind="prompt_opt")
        assert rows[0]["offered"] == 0
        assert rows[0]["bypass_reason"] == "short"

    def test_ts_defaults_to_now_when_omitted(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_prompt_opt_event

        db = tmp_path / "history.db"
        record_prompt_opt_event(db, session_id="sess-3", mode="quick", offered=True)
        rows = recent(db, kind="prompt_opt")
        assert rows[0]["ts"]

    def test_kwarg_only_signature(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_prompt_opt_event

        db = tmp_path / "history.db"
        with pytest.raises(TypeError):
            record_prompt_opt_event(db, "sess-4", True)  # type: ignore[misc]

    def test_raises_on_unopenable_db(self, tmp_path: Path) -> None:
        """Caller (user_prompt_submit.py) wraps this in contextlib.suppress(Exception)."""
        from little_loops.session_store import record_prompt_opt_event

        # tmp_path is a directory — sqlite cannot open it as a database file.
        with pytest.raises(sqlite3.Error):
            record_prompt_opt_event(tmp_path, session_id="sess-5", mode="quick", offered=True)

    def test_fts_indexed(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_prompt_opt_event

        db = tmp_path / "history.db"
        record_prompt_opt_event(
            db,
            ts="2026-07-23T00:00:00Z",
            session_id="unique-search-session-abc",
            mode="thorough",
            offered=True,
            bypass_reason="unique-fts-marker-xyz",
        )
        results = search(db, query="unique-fts-marker-xyz")
        assert any(r["kind"] == "prompt_opt" for r in results)


class TestRecordVerdictEvent:
    """ENH-2504: record_verdict_event() single-row INSERT."""

    def test_inserts_row_with_all_columns(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_verdict_event

        db = tmp_path / "history.db"
        record_verdict_event(
            db,
            ts="2026-07-23T00:00:00Z",
            session_id="sess-1",
            verdict_kind="ready-issue",
            target_kind="issue",
            target_id="BUG-2501",
            verdict="pass",
            severity_counts={"p0": 0, "p1": 2, "p2": 1},
            findings_count=3,
            confidence=97,
            head_sha="abc123",
            branch="main",
        )
        rows = recent(db, kind="verdict")
        assert len(rows) == 1
        row = rows[0]
        assert row["verdict_kind"] == "ready-issue"
        assert row["target_kind"] == "issue"
        assert row["target_id"] == "BUG-2501"
        assert row["verdict"] == "pass"
        assert json.loads(row["severity_counts"]) == {"p0": 0, "p1": 2, "p2": 1}
        assert row["findings_count"] == 3
        assert row["confidence"] == 97
        assert row["head_sha"] == "abc123"
        assert row["branch"] == "main"

    def test_severity_counts_none_round_trips_as_null(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_verdict_event

        db = tmp_path / "history.db"
        record_verdict_event(
            db,
            ts="2026-07-23T00:00:00Z",
            session_id=None,
            verdict_kind="go-no-go",
            verdict="fail",
        )
        rows = recent(db, kind="verdict")
        assert rows[0]["severity_counts"] is None

    def test_multiple_invocations_are_distinct_rows(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_verdict_event

        db = tmp_path / "history.db"
        record_verdict_event(
            db,
            ts="2026-07-23T00:00:00Z",
            session_id=None,
            verdict_kind="ready-issue",
            verdict="pass",
        )
        record_verdict_event(
            db,
            ts="2026-07-23T00:05:00Z",
            session_id=None,
            verdict_kind="ready-issue",
            verdict="fail",
        )
        rows = recent(db, kind="verdict")
        assert len(rows) == 2
        assert rows[0]["ts"] > rows[1]["ts"]

    def test_kwarg_only_signature(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_verdict_event

        db = tmp_path / "history.db"
        with pytest.raises(TypeError):
            record_verdict_event(db, "2026-07-23T00:00:00Z", "ready-issue", "pass")  # type: ignore[misc]

    def test_raises_on_unopenable_db(self, tmp_path: Path) -> None:
        """Best-effort is enforced at the cmd_invoke() call site, not the producer."""
        from little_loops.session_store import record_verdict_event

        with pytest.raises(sqlite3.Error):
            record_verdict_event(
                tmp_path,
                ts="2026-07-23T00:00:00Z",
                session_id=None,
                verdict_kind="ready-issue",
                verdict="pass",
            )

    def test_fts_indexed(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_verdict_event

        db = tmp_path / "history.db"
        record_verdict_event(
            db,
            ts="2026-07-23T00:00:00Z",
            session_id=None,
            verdict_kind="ready-issue",
            target_id="BUG-2501",
            verdict="pass",
        )
        results = search(db, query=fts_phrase("BUG-2501"))
        assert any(r["kind"] == "verdict" for r in results)

    def test_cannot_judge_writes_null_findings_count(self, tmp_path: Path) -> None:
        """ENH-230: the writer emits SQL NULL for findings_count on an abstention.

        Coalescing None to 0 at the writer would mask the abstention signal
        in every downstream reader — the schema pins findings_count nullable
        and the writer has to actively emit NULL, not 0.
        """
        import sqlite3

        from little_loops.session_store import record_verdict_event

        db = tmp_path / "history.db"
        record_verdict_event(
            db,
            ts="2026-07-23T00:00:00Z",
            session_id=None,
            verdict_kind="ready-issue",
            target_id="BUG-22",
            verdict="cannot_judge",
            abstention_reason="missing_artifacts",
        )

        conn = sqlite3.connect(db)
        try:
            row = conn.execute(
                "SELECT findings_count, confidence, abstention_reason "
                "FROM verdict_events WHERE target_id='BUG-22'"
            ).fetchone()
        finally:
            conn.close()
        assert row is not None
        findings_count, confidence, abstention_reason = row
        assert findings_count is None
        assert confidence is None
        assert abstention_reason == "missing_artifacts"

    def test_check_constraint_rejects_unknown_abstention_reason(self, tmp_path: Path) -> None:
        """ENH-230: the schema CHECK pins the four-tag enum; unknown tags fail the INSERT."""
        import sqlite3

        from little_loops.session_store import record_verdict_event

        db = tmp_path / "history.db"
        with pytest.raises(sqlite3.IntegrityError):
            record_verdict_event(
                db,
                ts="2026-07-23T00:00:00Z",
                session_id=None,
                verdict_kind="ready-issue",
                target_id="BUG-24",
                verdict="cannot_judge",
                abstention_reason="i_dunno",
            )

    def test_check_constraint_rejects_reason_on_non_abstention_verdict(
        self, tmp_path: Path
    ) -> None:
        """ENH-230: pass/fail/implement MUST NOT carry an abstention_reason."""
        import sqlite3

        from little_loops.session_store import record_verdict_event

        db = tmp_path / "history.db"
        with pytest.raises(sqlite3.IntegrityError):
            record_verdict_event(
                db,
                ts="2026-07-23T00:00:00Z",
                session_id=None,
                verdict_kind="ready-issue",
                target_id="BUG-25",
                verdict="pass",
                abstention_reason="missing_artifacts",
            )

    def test_check_constraint_rejects_refused_verdict(self, tmp_path: Path) -> None:
        """ENH-230: `refused` is review_events vocabulary (ENH-2512), not verdict_events.

        No verifier emits it. Admitting it in the CHECK would cost a table
        rebuild to walk back, so the grammar stays narrow until a producer
        exists.
        """
        import sqlite3

        from little_loops.session_store import record_verdict_event

        db = tmp_path / "history.db"
        with pytest.raises(sqlite3.IntegrityError):
            record_verdict_event(
                db,
                ts="2026-07-23T00:00:00Z",
                session_id=None,
                verdict_kind="ready-issue",
                target_id="BUG-26",
                verdict="refused",
            )

    def test_cannot_judge_round_trip_preserves_null_fields(self, tmp_path: Path) -> None:
        """ENH-230: None in -> SQL NULL on disk -> None back out of the reader.

        Nails the writer boundary that the consumer-side NULL contract in
        test_verdict_grammar_regression.py depends on.
        """
        import sqlite3

        from little_loops.history_reader import recent_verdict_events
        from little_loops.session_store import record_verdict_event

        db = tmp_path / "history.db"
        record_verdict_event(
            db,
            ts="2026-07-23T00:00:00Z",
            session_id=None,
            verdict_kind="ready-issue",
            target_id="BUG-27",
            verdict="cannot_judge",
            abstention_reason="evaluation_context_unavailable",
        )

        # Writer boundary — raw SQL NULL on findings_count and confidence.
        conn = sqlite3.connect(db)
        try:
            raw = conn.execute(
                "SELECT findings_count, confidence, abstention_reason, verdict "
                "FROM verdict_events WHERE target_id='BUG-27'"
            ).fetchone()
        finally:
            conn.close()
        assert raw is not None
        assert raw[0] is None  # findings_count
        assert raw[1] is None  # confidence
        assert raw[2] == "evaluation_context_unavailable"
        assert raw[3] == "cannot_judge"

        # Reader surface — recent_verdict_events surfaces None, not 0.
        rows = recent_verdict_events(db=db)
        assert len(rows) == 1
        assert rows[0].findings_count is None
        assert rows[0].confidence is None
        assert rows[0].abstention_reason == "evaluation_context_unavailable"


class TestRecordReviewEvent:
    """ENH-2512: record_review_event() single-row INSERT."""

    def test_inserts_row_with_all_columns(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_review_event

        db = tmp_path / "history.db"
        record_review_event(
            db,
            ts="2026-07-23T00:00:00Z",
            session_id="sess-1",
            reviewer_skill="audit-architecture",
            target_kind="repo",
            target_id=None,
            severity_counts={"p0": 1, "p1": 3, "p2": 7, "info": 12},
            findings_count=23,
            findings_json_summary={"top": [{"title": "God class", "file": "services.py"}]},
            verdict="warn",
            head_sha="abc123",
            branch="main",
        )
        rows = recent(db, kind="review")
        assert len(rows) == 1
        row = rows[0]
        assert row["reviewer_skill"] == "audit-architecture"
        assert row["target_kind"] == "repo"
        assert row["target_id"] is None
        assert json.loads(row["severity_counts"]) == {"p0": 1, "p1": 3, "p2": 7, "info": 12}
        assert row["findings_count"] == 23
        assert json.loads(row["findings_json_summary"]) == {
            "top": [{"title": "God class", "file": "services.py"}]
        }
        assert row["verdict"] == "warn"
        assert row["head_sha"] == "abc123"
        assert row["branch"] == "main"

    def test_severity_counts_none_round_trips_as_null(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_review_event

        db = tmp_path / "history.db"
        record_review_event(
            db,
            ts="2026-07-23T00:00:00Z",
            session_id=None,
            reviewer_skill="audit-loop-run",
            verdict="refused",
        )
        rows = recent(db, kind="review")
        assert rows[0]["severity_counts"] is None

    def test_refused_verdict_with_zero_findings(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_review_event

        db = tmp_path / "history.db"
        record_review_event(
            db,
            ts="2026-07-23T00:00:00Z",
            session_id=None,
            reviewer_skill="audit-loop-run",
            target_kind="loop",
            target_id="rn-implement",
            severity_counts={"p0": 0, "p1": 0, "p2": 0, "info": 0},
            findings_count=0,
            verdict="refused",
        )
        rows = recent(db, kind="review")
        assert rows[0]["verdict"] == "refused"
        assert rows[0]["findings_count"] == 0

    def test_multiple_invocations_are_distinct_rows(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_review_event

        db = tmp_path / "history.db"
        record_review_event(
            db,
            ts="2026-07-23T00:00:00Z",
            session_id=None,
            reviewer_skill="review-epic",
            verdict="pass",
        )
        record_review_event(
            db,
            ts="2026-07-23T00:05:00Z",
            session_id=None,
            reviewer_skill="review-epic",
            verdict="warn",
        )
        rows = recent(db, kind="review")
        assert len(rows) == 2
        assert rows[0]["ts"] > rows[1]["ts"]

    def test_kwarg_only_signature(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_review_event

        db = tmp_path / "history.db"
        with pytest.raises(TypeError):
            record_review_event(db, "2026-07-23T00:00:00Z", "audit-architecture", "pass")  # type: ignore[misc]

    def test_raises_on_unopenable_db(self, tmp_path: Path) -> None:
        """Best-effort is enforced at the cmd_invoke() call site, not the producer."""
        from little_loops.session_store import record_review_event

        with pytest.raises(sqlite3.Error):
            record_review_event(
                tmp_path,
                ts="2026-07-23T00:00:00Z",
                session_id=None,
                reviewer_skill="audit-architecture",
                verdict="pass",
            )

    def test_fts_indexed(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_review_event

        db = tmp_path / "history.db"
        record_review_event(
            db,
            ts="2026-07-23T00:00:00Z",
            session_id=None,
            reviewer_skill="review-epic",
            target_id="EPIC-2457",
            verdict="pass",
        )
        results = search(db, query=fts_phrase("EPIC-2457"))
        assert any(r["kind"] == "review" for r in results)


class TestRecordContextPressureEvent:
    """ENH-2507: record_context_pressure_event() DB write round-trip."""

    def test_roundtrip(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_context_pressure_event

        db = tmp_path / "history.db"
        assert record_context_pressure_event(
            db,
            session_id="s1",
            used_pct=42.5,
            used_tokens_est=85000,
        )
        rows = recent(db, kind="context_pressure")
        assert len(rows) == 1
        assert rows[0]["session_id"] == "s1"
        assert rows[0]["used_pct"] == 42.5
        assert rows[0]["used_tokens_est"] == 85000
        assert rows[0]["threshold_crossed"] == 0
        assert rows[0]["crossed_level"] is None

    def test_threshold_crossing_persists_level(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_context_pressure_event

        db = tmp_path / "history.db"
        record_context_pressure_event(
            db,
            session_id="s1",
            used_pct=81.0,
            used_tokens_est=162000,
            threshold_crossed=True,
            crossed_level="80",
            head_sha="abc123",
            branch="main",
        )
        rows = recent(db, kind="context_pressure")
        assert rows[0]["threshold_crossed"] == 1
        assert rows[0]["crossed_level"] == "80"
        assert rows[0]["head_sha"] == "abc123"
        assert rows[0]["branch"] == "main"

    def test_multiple_invocations_are_distinct_rows(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_context_pressure_event

        db = tmp_path / "history.db"
        record_context_pressure_event(db, session_id="s1", used_pct=10.0, used_tokens_est=1000)
        record_context_pressure_event(db, session_id="s1", used_pct=20.0, used_tokens_est=2000)
        rows = recent(db, kind="context_pressure")
        assert len(rows) == 2

    def test_fts_indexed(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_context_pressure_event

        db = tmp_path / "history.db"
        record_context_pressure_event(
            db,
            session_id="sess-fts-pressure",
            used_pct=55.0,
            used_tokens_est=110000,
        )
        results = search(db, query=fts_phrase("sess-fts-pressure"))
        assert any(r["kind"] == "context_pressure" for r in results)

    def test_graceful_when_store_unwritable(self, tmp_path: Path, monkeypatch) -> None:
        import little_loops.session_store as session_store

        def boom(*_args, **_kwargs):  # type: ignore[no-untyped-def]
            raise sqlite3.OperationalError("database is locked")

        monkeypatch.setattr(session_store, "connect", boom)

        db = tmp_path / "history.db"
        assert not session_store.record_context_pressure_event(
            db, session_id="s1", used_pct=10.0, used_tokens_est=1000
        )


class TestWriteAdvisorConsult:
    """FEAT-3300: write_advisor_consult() persists advisor_consults rows."""

    def test_issued_consult_persists_all_fields(self, tmp_path: Path) -> None:
        from little_loops.session_store import write_advisor_consult

        db = tmp_path / "history.db"
        assert write_advisor_consult(
            db,
            session_id="s1",
            task_key="issue:FEAT-3300",
            signal="confidence_gate",
            advisor_host="claude-code",
            advisor_model="claude-opus-5",
            main_model="claude-sonnet-5",
            outcome="issued",
            floor_status="ok",
            latency_ms=4200,
            confidence=0.9,
        )
        rows = recent(db, kind="advisor_consult")
        assert rows[0]["outcome"] == "issued"
        assert rows[0]["task_key"] == "issue:FEAT-3300"
        assert rows[0]["signal"] == "confidence_gate"
        assert rows[0]["advisor_host"] == "claude-code"
        assert rows[0]["latency_ms"] == 4200
        assert rows[0]["input_tokens"] is None
        assert rows[0]["output_tokens"] is None
        assert rows[0]["verdict_body"] is None

    def test_skipped_consult_persists_outcome_reason(self, tmp_path: Path) -> None:
        from little_loops.session_store import write_advisor_consult

        db = tmp_path / "history.db"
        assert write_advisor_consult(
            db,
            session_id="s1",
            task_key="session:abc",
            signal="loop_stall",
            advisor_host=None,
            advisor_model=None,
            main_model="claude-sonnet-5",
            outcome="budget_exhausted",
        )
        rows = recent(db, kind="advisor_consult")
        assert rows[0]["outcome"] == "budget_exhausted"
        assert rows[0]["advisor_host"] is None
        assert rows[0]["latency_ms"] is None

    def test_verdict_body_absent_unless_passed(self, tmp_path: Path) -> None:
        from little_loops.session_store import write_advisor_consult

        db = tmp_path / "history.db"
        write_advisor_consult(
            db,
            session_id="s1",
            task_key="session:abc",
            signal="pre_done",
            advisor_host="claude-code",
            advisor_model="claude-opus-5",
            main_model="claude-sonnet-5",
            outcome="issued",
        )
        rows = recent(db, kind="advisor_consult")
        assert rows[0]["verdict_body"] is None

    def test_graceful_when_store_unwritable(self, tmp_path: Path, monkeypatch) -> None:
        import little_loops.session_store as session_store

        def boom(*_args, **_kwargs):  # type: ignore[no-untyped-def]
            raise sqlite3.OperationalError("database is locked")

        monkeypatch.setattr(session_store, "connect", boom)

        db = tmp_path / "history.db"
        assert not session_store.write_advisor_consult(
            db,
            session_id="s1",
            task_key="session:abc",
            signal="pre_done",
            advisor_host="claude-code",
            advisor_model="claude-opus-5",
            main_model="claude-sonnet-5",
            outcome="issued",
        )
