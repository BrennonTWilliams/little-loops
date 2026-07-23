"""Tests for fsm/continuity.py (FEAT-2711): FSM-side continuity-chain compaction wiring.

Promoted from the spike's TestBackfillThenCompact/TestSummaryIncludesAssistantContent
suite (scripts/tests/spike/fsm_continuity_compaction/test_continuity_pipeline.py),
adapted to exercise the production `summarize_completed_state()` entry point instead
of the spike's `backfill_and_compact()`.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from little_loops.fsm.continuity import summarize_completed_state

SESSION_ID = "continuity-test-session"
USER_TURN = "Read scripts/little_loops/config.py and summarize its schema."
ASSISTANT_TURN = (
    "The schema has fields: id (int), name (str), created_at (datetime), validated "
    "against a slug regex by the loader."
)


def _write_transcript(tmp_path: Path) -> Path:
    lines = [
        json.dumps(
            {
                "type": "user",
                "sessionId": SESSION_ID,
                "timestamp": "2026-07-23T00:00:00Z",
                "message": {"content": USER_TURN},
            }
        ),
        json.dumps(
            {
                "type": "assistant",
                "sessionId": SESSION_ID,
                "timestamp": "2026-07-23T00:00:05Z",
                "message": {"content": [{"type": "text", "text": ASSISTANT_TURN}]},
            }
        ),
    ]
    jsonl_path = tmp_path / f"{SESSION_ID}.jsonl"
    jsonl_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return jsonl_path


class TestSummarizeCompletedState:
    def test_returns_none_when_project_folder_missing(self, tmp_path: Path) -> None:
        """No project folder on disk -> None, no exception (FEAT-2711 fail-soft contract)."""
        with patch("little_loops.fsm.continuity.get_project_folder", return_value=None):
            result = summarize_completed_state(SESSION_ID, db=tmp_path / "history.db")
        assert result is None

    def test_returns_none_when_transcript_missing(self, tmp_path: Path) -> None:
        """Project folder exists but has no matching <session_id>.jsonl -> None."""
        project_folder = tmp_path / "project"
        project_folder.mkdir()
        with patch("little_loops.fsm.continuity.get_project_folder", return_value=project_folder):
            result = summarize_completed_state(SESSION_ID, db=tmp_path / "history.db")
        assert result is None

    def test_backfills_and_compacts_with_assistant_content(self, tmp_path: Path) -> None:
        """The assistant-inclusive summary carries forward both user and assistant turns."""
        db = tmp_path / "history.db"
        project_folder = tmp_path / "project"
        project_folder.mkdir()
        _write_transcript(project_folder)

        with patch("little_loops.fsm.continuity.get_project_folder", return_value=project_folder):
            with patch("little_loops.session_store.subprocess.run") as mock_run:
                mock_run.return_value.returncode = 0
                mock_run.return_value.stdout = json.dumps(
                    {"type": "result", "subtype": "success", "result": "Mocked summary."}
                )
                mock_run.return_value.stderr = ""
                result = summarize_completed_state(
                    SESSION_ID,
                    db=db,
                    config={"history": {"compaction": {"enabled": True, "budget_tokens": 50}}},
                )

                prompts_seen = [
                    call.args[0][call.args[0].index("-p") + 1]
                    for call in mock_run.call_args_list
                    if "-p" in call.args[0]
                ]

        assert result is not None
        combined_prompts = "\n".join(prompts_seen)
        assert USER_TURN in combined_prompts
        assert ASSISTANT_TURN in combined_prompts
