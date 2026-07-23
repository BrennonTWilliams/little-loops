"""AC tests for the FEAT-2711 Option B (compact-summary injection) spike.

See `.ll/spikes/spike-FEAT-2711.md` § Acceptance Criteria -> Test Table.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from unittest.mock import patch

from tests.spike.fsm_continuity_compaction.continuity_pipeline import backfill_and_compact
from tests.spike.fsm_continuity_compaction.session_id_capture import (
    parse_session_id_from_stream_json,
)

SESSION_ID = "spike-test-session"
USER_TURN_1 = (
    "Read scripts/little_loops/config.py end to end and summarize every field of "
    "the schema it defines, including defaults, validation rules, and how each "
    "field is consumed downstream by the loader and the CLI resolver."
)
ASSISTANT_TURN_1 = (
    "The schema has fields: id (int), name (str), created_at (datetime). "
    "A foreign key to accounts.id enforces referential integrity. The loader "
    "validates name against a slug regex and raises ConfigError on mismatch, "
    "while created_at defaults to the current UTC timestamp when omitted."
)
USER_TURN_2 = (
    "Now check that same table for any missing indexes on the foreign key "
    "column and any other column used in a frequent WHERE clause filter."
)


def _transcript_lines() -> list[str]:
    return [
        json.dumps(
            {
                "type": "user",
                "sessionId": SESSION_ID,
                "timestamp": "2026-07-21T00:00:00Z",
                "message": {"content": USER_TURN_1},
            }
        ),
        json.dumps(
            {
                "type": "assistant",
                "sessionId": SESSION_ID,
                "timestamp": "2026-07-21T00:00:05Z",
                "message": {"content": [{"type": "text", "text": ASSISTANT_TURN_1}]},
            }
        ),
        json.dumps(
            {
                "type": "user",
                "sessionId": SESSION_ID,
                "timestamp": "2026-07-21T00:01:00Z",
                "message": {"content": USER_TURN_2},
            }
        ),
    ]


def _write_transcript(tmp_path: Path) -> Path:
    jsonl_path = tmp_path / f"{SESSION_ID}.jsonl"
    jsonl_path.write_text("\n".join(_transcript_lines()) + "\n", encoding="utf-8")
    return jsonl_path


class TestSessionIdCapture:
    """Risk (a): zero precedent for FSM-side session-ID capture."""

    def test_parses_session_id_from_init_event(self) -> None:
        line = json.dumps(
            {"type": "system", "subtype": "init", "session_id": "abc-123", "model": "claude-x"}
        )
        assert parse_session_id_from_stream_json(line) == "abc-123"

    def test_ignores_non_init_events(self) -> None:
        line = json.dumps({"type": "assistant", "message": {"content": []}})
        assert parse_session_id_from_stream_json(line) is None

    def test_ignores_malformed_json(self) -> None:
        assert parse_session_id_from_stream_json("not json") is None


class TestBackfillThenCompact:
    """Risk (b): unproven synchronous in-process backfill+compact for a just-finished session."""

    def test_backfill_then_compact_same_process_no_race(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        jsonl_path = _write_transcript(tmp_path)

        with patch("little_loops.session_store.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = json.dumps(
                {"type": "result", "subtype": "success", "result": "Mocked summary."}
            )
            mock_run.return_value.stderr = ""
            result = backfill_and_compact(
                db,
                SESSION_ID,
                jsonl_path,
                config={"history": {"compaction": {"enabled": True, "budget_tokens": 50}}},
            )

        # No backfill CLI call, no wait, no polling loop — this call returning
        # a non-None CompactResult in the same process proves the pipeline can
        # run synchronously right after a session's JSONL is on disk.
        assert result is not None
        assert "Mocked summary." in result.summary_text

    def test_compact_returns_none_without_backfill(self, tmp_path: Path) -> None:
        """Compacting a session that was never backfilled (message_events empty) yields None."""
        from little_loops.compaction.result import compact_result_for_session
        from little_loops.session_store import compact_session, connect

        db = tmp_path / "history.db"
        conn = connect(db)
        conn.close()

        compact_session(SESSION_ID, db, config={"history": {"compaction": {"enabled": True}}})
        assert compact_result_for_session(SESSION_ID, db) is None


class TestSummaryOmitsAssistantContent:
    """Additional risk: compact_session() reads only message_events (user turns)."""

    def test_compact_summary_omits_assistant_derived_content(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        jsonl_path = _write_transcript(tmp_path)

        with patch("little_loops.session_store.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = json.dumps(
                {"type": "result", "subtype": "success", "result": "Mocked summary."}
            )
            mock_run.return_value.stderr = ""
            backfill_and_compact(
                db,
                SESSION_ID,
                jsonl_path,
                config={"history": {"compaction": {"enabled": True, "budget_tokens": 50}}},
            )

            # Inspect every prompt actually sent to the (mocked) summarizer CLI.
            prompts_seen = [
                call.args[0][call.args[0].index("-p") + 1]
                for call in mock_run.call_args_list
                if "-p" in call.args[0]
            ]

        combined_prompts = "\n".join(prompts_seen)
        assert USER_TURN_1 in combined_prompts
        assert USER_TURN_2 in combined_prompts
        # The assistant's derived understanding never reaches the summarizer:
        # compact_session() only queries message_events (user-only), never
        # assistant_messages. This is the gap the issue's Decision Rationale
        # did not account for when it costed Option B as "reuse of mature,
        # tested primitives."
        assert ASSISTANT_TURN_1 not in combined_prompts


class TestSummaryIncludesAssistantContent:
    """FEAT-2747: the assistant-inclusive counterpart closes the gap above."""

    def test_compact_with_reasoning_includes_assistant_derived_content(
        self, tmp_path: Path
    ) -> None:
        from little_loops.compaction.result import compact_result_for_session_with_reasoning
        from little_loops.session_store import (
            _backfill_assistant_messages,
            _backfill_messages,
            connect,
        )

        db = tmp_path / "history.db"
        jsonl_path = _write_transcript(tmp_path)

        with patch("little_loops.session_store.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = json.dumps(
                {"type": "result", "subtype": "success", "result": "Mocked summary."}
            )
            mock_run.return_value.stderr = ""

            conn = connect(db)
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO sessions(session_id, jsonl_path) VALUES(?, ?)",
                    (SESSION_ID, str(jsonl_path)),
                )
                _backfill_messages(conn, [jsonl_path])
                _backfill_assistant_messages(conn, [jsonl_path])
                conn.commit()
            finally:
                conn.close()

            result = compact_result_for_session_with_reasoning(SESSION_ID, db)

            prompts_seen = [
                call.args[0][call.args[0].index("-p") + 1]
                for call in mock_run.call_args_list
                if "-p" in call.args[0]
            ]

        assert result is not None
        combined_prompts = "\n".join(prompts_seen)
        assert USER_TURN_1 in combined_prompts
        assert USER_TURN_2 in combined_prompts
        # Inverted from TestSummaryOmitsAssistantContent above: the
        # assistant-inclusive function must forward the assistant turn too.
        assert ASSISTANT_TURN_1 in combined_prompts


class TestSpikeIsolation:
    """Regression guard: the spike must not import FSM production modules."""

    def test_spike_does_not_import_fsm_production_modules(self) -> None:
        spike_dir = Path(__file__).parent
        forbidden_prefixes = ("little_loops.fsm",)
        for py_file in spike_dir.glob("*.py"):
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    assert not node.module.startswith(forbidden_prefixes), (
                        f"{py_file.name} imports forbidden module {node.module!r}"
                    )
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        assert not alias.name.startswith(forbidden_prefixes), (
                            f"{py_file.name} imports forbidden module {alias.name!r}"
                        )
