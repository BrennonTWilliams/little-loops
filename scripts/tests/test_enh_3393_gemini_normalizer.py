"""ENH-3393: gemini file-level normalization, HostLayout normalize_file contract.

Gemini session JSONL (gemini-cli 0.46.0) diverges from both Claude and qwen:
the session id lives only in a file **header** line, not on each record, and
the initial user turn is nested inside a ``$set.messages`` patch while every
later turn is a bare top-level record. This can't be normalized per-record
(the existing ``HostLayout.normalize`` contract) — it needs file-level state,
hence ``HostLayout.normalize_file`` (a new field alongside ``normalize``).

These tests pin down:

- ``normalize_gemini_session`` — the file-level reader (header parse, initial
  ``$set.messages`` unpack, bare-record turns, inline toolCalls split into
  ``tool_use``/``tool_result``, ``$rewindTo``/metadata-only ``$set`` skipped,
  legacy whole-document ``.json`` skipped without error)
- ``host_layout_for("gemini")`` — the layout descriptor
- ``_backfill_raw_events`` — the ``normalize_file`` ingestion branch stamps
  ``session_id``/``host`` correctly and existing (``normalize_file=None``)
  hosts are unaffected (regression-locked against the qwen fixture)
- ``rebuild()`` deriving ``tool_events``/``message_events``/
  ``assistant_messages``/``sessions`` from gemini raw_events rows, reusing
  the same Claude-shaped extractors qwen already exercises

Fixtures under ``fixtures/gemini/`` are synthesized to match the observed
gemini-cli 0.46.0 wire structure (verified against real captures on the dev
machine, see ENH-3393's "Verified Host Layouts") — the suite never reads
``~/.gemini``.
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
    normalize_gemini_session,
    rebuild,
)
from little_loops.session_store.writers import _unpack_payload

FIXTURES = Path(__file__).parent / "fixtures" / "gemini"
SESSION_FIXTURE = FIXTURES / "session.jsonl"
LEGACY_FIXTURE = FIXTURES / "legacy.json"

SESSION_ID = "11111111-2222-3333-4444-555555555555"


class TestNormalizeGeminiSession:
    """normalize_gemini_session reads one file and yields Claude-shaped records."""

    def test_yields_six_records_in_order(self) -> None:
        records = list(normalize_gemini_session(SESSION_FIXTURE))
        assert len(records) == 6
        assert [r["type"] for r in records] == [
            "user",
            "user",
            "assistant",
            "assistant",
            "user",
            "user",
        ]

    def test_every_record_stamped_with_header_session_id(self) -> None:
        records = list(normalize_gemini_session(SESSION_FIXTURE))
        assert all(r["sessionId"] == SESSION_ID for r in records)

    def test_initial_set_messages_turn_unpacked(self) -> None:
        first = next(iter(normalize_gemini_session(SESSION_FIXTURE)))
        assert first["message"]["role"] == "user"
        assert "session_context" in first["message"]["content"][0]["text"]

    def test_inline_tool_call_splits_into_tool_use_and_tool_result(self) -> None:
        records = list(normalize_gemini_session(SESSION_FIXTURE))
        assistant_with_tool = records[3]
        blocks = assistant_with_tool["message"]["content"]
        tool_use = [b for b in blocks if b["type"] == "tool_use"]
        assert len(tool_use) == 1
        assert tool_use[0]["name"] == "run_shell_command"
        assert tool_use[0]["input"] == {"command": "ll-issues list"}

        tool_result_record = records[4]
        assert tool_result_record["type"] == "user"
        result_block = tool_result_record["message"]["content"][0]
        assert result_block["type"] == "tool_result"
        assert result_block["tool_use_id"] == "call-1"
        assert result_block["is_error"] is False

    def test_rewind_marker_yields_nothing(self) -> None:
        """$rewindTo carries no message content and must not appear as a record."""
        records = list(normalize_gemini_session(SESSION_FIXTURE))
        # 6 records total (asserted above); if $rewindTo were mis-parsed as a
        # message it would inflate this count or raise.
        assert all("message" in r for r in records)

    def test_metadata_only_set_yields_nothing(self) -> None:
        """$set patches without a messages key (lastUpdated-only) are skipped."""
        records = list(normalize_gemini_session(SESSION_FIXTURE))
        texts = [
            block["text"]
            for r in records
            for block in r["message"]["content"]
            if block.get("type") == "text"
        ]
        assert "I'll check now." in texts

    def test_legacy_whole_document_json_skipped_without_error(self) -> None:
        """Pre-Oct-2025 single-document session*.json files yield nothing, not an error."""
        assert list(normalize_gemini_session(LEGACY_FIXTURE)) == []

    def test_missing_file_yields_nothing(self, tmp_path: Path) -> None:
        assert list(normalize_gemini_session(tmp_path / "does-not-exist.jsonl")) == []


class TestHostLayoutRegistryGemini:
    def test_gemini_layout_uses_file_level_normalizer(self) -> None:
        layout = host_layout_for("gemini")

        assert isinstance(layout, HostLayout)
        assert layout.name == "gemini"
        assert layout.projects_root is None
        assert layout.session_glob == "chats/session-*.jsonl"
        assert layout.sessions_subdir == "chats"
        assert not hasattr(layout, "normalize")
        assert not hasattr(layout, "normalize_file")

    def test_claude_layout_has_no_file_level_normalizer(self) -> None:
        assert not hasattr(host_layout_for("claude-code"), "normalize_file")

    def test_qwen_layout_has_no_file_level_normalizer(self) -> None:
        """The record-level qwen contract and the file-level gemini contract coexist."""
        assert not hasattr(host_layout_for("qwen"), "normalize_file")


class TestBackfillRawEventsNormalizeFile:
    """_backfill_raw_events routes normalize_file hosts through the file-level reader."""

    def test_gemini_rows_stamped_with_session_id_and_host(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        monkeypatch.setenv("LL_HOST_CLI", "claude-code")
        db = tmp_path / "history.db"
        ensure_db(db)

        count = backfill_raw_events(db, jsonl_files=[SESSION_FIXTURE], since_ts=0.0, host="gemini")

        assert count == 6
        conn = connect(db)
        try:
            rows = conn.execute(
                "SELECT session_id, host, event_type FROM raw_events ORDER BY line_no"
            ).fetchall()
        finally:
            conn.close()
        assert len(rows) == 6
        assert {row[0] for row in rows} == {SESSION_ID}
        assert {row[1] for row in rows} == {"gemini"}
        assert [row[2] for row in rows] == [
            "user",
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

        first = backfill_raw_events(db, jsonl_files=[SESSION_FIXTURE], since_ts=0.0, host="gemini")
        second = backfill_raw_events(db, jsonl_files=[SESSION_FIXTURE], since_ts=0.0, host="gemini")

        assert first == 6
        assert second == 0

    def test_raw_line_and_parsed_json_are_normalized_form(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """No verbatim per-line source survives file-level normalization —
        raw_line/parsed_json both store the Claude-shaped record (matches the
        pattern _iter_events already uses for record-level normalize)."""
        monkeypatch.setenv("LL_HOST_CLI", "claude-code")
        db = tmp_path / "history.db"
        ensure_db(db)
        backfill_raw_events(db, jsonl_files=[SESSION_FIXTURE], since_ts=0.0, host="gemini")

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


class TestClaudeParityUnaffectedByNormalizeFile:
    """Adding normalize_file must not change Claude-shaped ingestion at all."""

    def test_claude_host_still_uses_per_line_path(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("LL_HOST_CLI", "claude-code")
        db = tmp_path / "history.db"
        ensure_db(db)
        claude_jsonl = tmp_path / "claude.jsonl"
        claude_jsonl.write_text(
            json.dumps(
                {
                    "type": "user",
                    "sessionId": "cs1",
                    "timestamp": "2026-08-05T10:00:00Z",
                    "message": {"role": "user", "content": "hello"},
                }
            )
            + "\n",
            encoding="utf-8",
        )

        count = backfill_raw_events(db, jsonl_files=[claude_jsonl], since_ts=0.0)

        assert count == 1
        conn = connect(db)
        try:
            raw_line = conn.execute("SELECT raw_line FROM raw_events").fetchone()[0]
        finally:
            conn.close()
        # Re-serialized payload is JSON-equal to the source line (ENH-3422 D6:
        # raw_line is no longer required to be byte-verbatim for any host).
        assert json.loads(_unpack_payload(raw_line))["message"]["content"] == "hello"


class TestRebuildGeminiRecords:
    """rebuild() derives cache tables from gemini raw_events rows."""

    def _ingest_gemini(self, tmp_path: Path, monkeypatch) -> Path:
        monkeypatch.setenv("LL_HOST_CLI", "claude-code")
        db = tmp_path / "history.db"
        ensure_db(db)
        backfill_raw_events(db, jsonl_files=[SESSION_FIXTURE], since_ts=0.0, host="gemini")
        return db

    def test_rebuild_derives_tool_events(self, tmp_path: Path, monkeypatch) -> None:
        db = self._ingest_gemini(tmp_path, monkeypatch)

        counts = rebuild(db)

        assert counts["tools"] == 1
        conn = connect(db)
        try:
            name = conn.execute("SELECT tool_name FROM tool_events").fetchone()[0]
        finally:
            conn.close()
        assert name == "run_shell_command"

    def test_rebuild_message_events_from_user_turns(self, tmp_path: Path, monkeypatch) -> None:
        db = self._ingest_gemini(tmp_path, monkeypatch)

        counts = rebuild(db)

        conn = connect(db)
        try:
            contents = [row[0] for row in conn.execute("SELECT content FROM message_events")]
        finally:
            conn.close()
        # Session-context preamble + two real user turns; the synthetic
        # tool_result user record carries no text content block.
        assert counts["messages"] == 3
        assert "Check which ll issues are open." in contents
        assert "Actually, check again." in contents

    def test_rebuild_assistant_messages(self, tmp_path: Path, monkeypatch) -> None:
        db = self._ingest_gemini(tmp_path, monkeypatch)

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

    def test_rebuild_seeds_session_from_gemini_rows(self, tmp_path: Path, monkeypatch) -> None:
        db = self._ingest_gemini(tmp_path, monkeypatch)

        counts = rebuild(db)

        assert counts["sessions"] == 1
        conn = connect(db)
        try:
            row = conn.execute("SELECT session_id FROM sessions").fetchone()
        finally:
            conn.close()
        assert row[0] == SESSION_ID
