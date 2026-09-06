"""ENH-3394: omp (oh-my-pi) file-level normalization, HostLayout normalize_file contract.

omp session JSONL (omp 18.0.11) diverges from both Claude and gemini: a
fixed-width title slot precedes the session header on every physical file,
the session id lives only in that header (not on each record, like gemini —
hence reusing ``HostLayout.normalize_file`` from ENH-3393), and each
conversational line's ``message.role`` is one of ``user``/``developer``/
``assistant``/``toolResult`` rather than Claude's flat user/assistant split.
Tool calls are inline on assistant turns (``toolCall`` blocks); tool
*results* are a separate ``toolResult``-role entry, unlike gemini's inline
``toolCalls[].result``.

These tests pin down:

- ``normalize_omp_session`` — the file-level reader (title-slot/header
  tolerance, plain-string and block-list user content, inline ``toolCall``
  split into a Claude ``tool_use`` block, the separate ``toolResult`` entry
  split into a synthetic Claude ``tool_result`` user turn, non-conversational
  entry types skipped, missing file yields nothing)
- ``host_layout_for("omp")`` — the layout descriptor
- ``_backfill_raw_events`` — the ``normalize_file`` ingestion branch stamps
  ``session_id``/``host`` correctly for omp
- ``rebuild()`` deriving ``tool_events``/``message_events``/
  ``assistant_messages``/``sessions`` from omp raw_events rows

Fixtures under ``fixtures/omp/`` are synthesized from the vendored
``@oh-my-pi/pi-coding-agent`` ``session-entries.ts``/``session-manager.ts``
types (omp 18.0.11) — omp has no real session captures on the ENH-3394 dev
machine, so these are not sanitized real captures (unlike gemini's).
"""

from __future__ import annotations

import json
from pathlib import Path

from little_loops.session_store import (
    HostLayout,
    backfill_raw_events,
    connect,
    ensure_db,
    host_layout_for,
    normalize_omp_session,
    rebuild,
)
from little_loops.session_store.writers import _unpack_payload

FIXTURES = Path(__file__).parent / "fixtures" / "omp"
SESSION_FIXTURE = FIXTURES / "session.jsonl"
LEGACY_FIXTURE = FIXTURES / "legacy_no_title_slot.jsonl"

SESSION_ID = "11111111-2222-3333-4444-555555555555"
LEGACY_SESSION_ID = "22222222-3333-4444-5555-666666666666"


class TestNormalizeOmpSession:
    """normalize_omp_session reads one file and yields Claude-shaped records."""

    def test_yields_five_records_in_order(self) -> None:
        records = list(normalize_omp_session(SESSION_FIXTURE))
        assert len(records) == 5
        assert [r["type"] for r in records] == [
            "user",
            "assistant",
            "assistant",
            "user",
            "user",
        ]

    def test_every_record_stamped_with_header_session_id(self) -> None:
        records = list(normalize_omp_session(SESSION_FIXTURE))
        assert all(r["sessionId"] == SESSION_ID for r in records)

    def test_plain_string_user_content_becomes_text_block(self) -> None:
        first = next(iter(normalize_omp_session(SESSION_FIXTURE)))
        assert first["message"]["role"] == "user"
        assert first["message"]["content"] == [
            {"type": "text", "text": "Check which ll issues are open."}
        ]

    def test_assistant_without_tool_call_has_no_tool_use_block(self) -> None:
        records = list(normalize_omp_session(SESSION_FIXTURE))
        assistant_plain = records[1]
        assert assistant_plain["message"]["content"] == [
            {"type": "text", "text": "I'll check now."}
        ]

    def test_inline_tool_call_becomes_tool_use_block(self) -> None:
        records = list(normalize_omp_session(SESSION_FIXTURE))
        assistant_with_tool = records[2]
        blocks = assistant_with_tool["message"]["content"]
        tool_use = [b for b in blocks if b["type"] == "tool_use"]
        assert len(tool_use) == 1
        assert tool_use[0]["name"] == "run_shell_command"
        assert tool_use[0]["input"] == {"command": "ll-issues list"}

    def test_tool_result_entry_splits_into_synthetic_user_turn(self) -> None:
        records = list(normalize_omp_session(SESSION_FIXTURE))
        tool_result_record = records[3]
        assert tool_result_record["type"] == "user"
        result_block = tool_result_record["message"]["content"][0]
        assert result_block["type"] == "tool_result"
        assert result_block["tool_use_id"] == "call-1"
        assert result_block["content"] == "BUG-1 open"
        assert result_block["is_error"] is False

    def test_non_conversational_entries_yield_nothing(self) -> None:
        """thinking_level_change/model_change carry no message content."""
        records = list(normalize_omp_session(SESSION_FIXTURE))
        # 5 records total (asserted above); if either were mis-parsed as a
        # message it would inflate this count or raise.
        assert all("message" in r for r in records)

    def test_legacy_file_without_title_slot_still_parses(self) -> None:
        """A v1/legacy file with no leading title-slot line still resolves the
        header — normalize_omp_session scans for the first `type: "session"`
        line rather than assuming a fixed position."""
        records = list(normalize_omp_session(LEGACY_FIXTURE))
        assert len(records) == 1
        assert records[0]["sessionId"] == LEGACY_SESSION_ID
        assert records[0]["message"]["content"] == [
            {"type": "text", "text": "Hello from a v1 session."}
        ]

    def test_missing_file_yields_nothing(self, tmp_path: Path) -> None:
        assert list(normalize_omp_session(tmp_path / "does-not-exist.jsonl")) == []


class TestHostLayoutRegistryOmp:
    def test_omp_layout_uses_file_level_normalizer(self) -> None:
        layout = host_layout_for("omp")

        assert isinstance(layout, HostLayout)
        assert layout.name == "omp"
        assert layout.projects_root is None
        assert layout.session_glob == "*.jsonl"
        assert layout.sessions_subdir == ""
        assert layout.normalize is None
        assert layout.normalize_file is normalize_omp_session

    def test_claude_layout_has_no_file_level_normalizer(self) -> None:
        assert host_layout_for("claude-code").normalize_file is None

    def test_gemini_layout_has_no_omp_normalizer(self) -> None:
        """The gemini and omp file-level contracts coexist without leaking."""
        from little_loops.session_store import normalize_gemini_session

        assert host_layout_for("gemini").normalize_file is normalize_gemini_session
        assert host_layout_for("gemini").normalize_file is not normalize_omp_session


class TestBackfillRawEventsNormalizeFileOmp:
    """_backfill_raw_events routes normalize_file hosts through the file-level reader."""

    def test_omp_rows_stamped_with_session_id_and_host(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("LL_HOST_CLI", "claude-code")
        db = tmp_path / "history.db"
        ensure_db(db)

        count = backfill_raw_events(db, jsonl_files=[SESSION_FIXTURE], since_ts=0.0, host="omp")

        assert count == 5
        conn = connect(db)
        try:
            rows = conn.execute(
                "SELECT session_id, host, event_type FROM raw_events ORDER BY line_no"
            ).fetchall()
        finally:
            conn.close()
        assert len(rows) == 5
        assert {row[0] for row in rows} == {SESSION_ID}
        assert {row[1] for row in rows} == {"omp"}
        assert [row[2] for row in rows] == [
            "user",
            "assistant",
            "assistant",
            "user",
            "user",
        ]

    def test_repeated_ingest_is_idempotent(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("LL_HOST_CLI", "claude-code")
        db = tmp_path / "history.db"
        ensure_db(db)

        first = backfill_raw_events(db, jsonl_files=[SESSION_FIXTURE], since_ts=0.0, host="omp")
        second = backfill_raw_events(db, jsonl_files=[SESSION_FIXTURE], since_ts=0.0, host="omp")

        assert first == 5
        assert second == 0

    def test_raw_line_and_parsed_json_are_normalized_form(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        monkeypatch.setenv("LL_HOST_CLI", "claude-code")
        db = tmp_path / "history.db"
        ensure_db(db)
        backfill_raw_events(db, jsonl_files=[SESSION_FIXTURE], since_ts=0.0, host="omp")

        conn = connect(db)
        try:
            raw_line, parsed_json = conn.execute(
                "SELECT raw_line, parsed_json FROM raw_events ORDER BY line_no LIMIT 1"
            ).fetchone()
        finally:
            conn.close()
        raw = json.loads(_unpack_payload(raw_line))
        parsed = json.loads(_unpack_payload(parsed_json))
        assert raw["sessionId"] == SESSION_ID
        assert parsed == raw


class TestRebuildOmpRecords:
    """rebuild() derives cache tables from omp raw_events rows."""

    def _ingest_omp(self, tmp_path: Path, monkeypatch) -> Path:
        monkeypatch.setenv("LL_HOST_CLI", "claude-code")
        db = tmp_path / "history.db"
        ensure_db(db)
        backfill_raw_events(db, jsonl_files=[SESSION_FIXTURE], since_ts=0.0, host="omp")
        return db

    def test_rebuild_derives_tool_events(self, tmp_path: Path, monkeypatch) -> None:
        db = self._ingest_omp(tmp_path, monkeypatch)

        counts = rebuild(db)

        assert counts["tools"] == 1
        conn = connect(db)
        try:
            name = conn.execute("SELECT tool_name FROM tool_events").fetchone()[0]
        finally:
            conn.close()
        assert name == "run_shell_command"

    def test_rebuild_message_events_from_user_turns(self, tmp_path: Path, monkeypatch) -> None:
        db = self._ingest_omp(tmp_path, monkeypatch)

        counts = rebuild(db)

        conn = connect(db)
        try:
            contents = [row[0] for row in conn.execute("SELECT content FROM message_events")]
        finally:
            conn.close()
        # Two real user turns; the synthetic tool_result user record carries
        # no plain "text" content block, so it contributes nothing here.
        assert counts["messages"] == 2
        assert "Check which ll issues are open." in contents
        assert "Actually, check again." in contents

    def test_rebuild_assistant_messages(self, tmp_path: Path, monkeypatch) -> None:
        db = self._ingest_omp(tmp_path, monkeypatch)

        counts = rebuild(db)

        assert counts["assistant_messages"] == 2
        conn = connect(db)
        try:
            rows = conn.execute(
                "SELECT content, tool_use_count FROM assistant_messages ORDER BY ts"
            ).fetchall()
        finally:
            conn.close()
        assert tuple(rows[0]) == ("I'll check now.", 0)
        assert tuple(rows[1]) == ("Let me run the command.", 1)

    def test_rebuild_seeds_session_from_omp_rows(self, tmp_path: Path, monkeypatch) -> None:
        db = self._ingest_omp(tmp_path, monkeypatch)

        counts = rebuild(db)

        assert counts["sessions"] == 1
        conn = connect(db)
        try:
            row = conn.execute("SELECT session_id FROM sessions").fetchone()
        finally:
            conn.close()
        assert row[0] == SESSION_ID
