"""Spike driver: exercise the continuity pipeline end-to-end against a fixture transcript.

Run directly (``python -m spike.fsm_continuity_compaction.driver`` from
``scripts/tests/``) to see the resulting ``summary_text`` printed. Uses a
real (temp, throwaway) sqlite db and a mocked LLM summarizer — no live host
CLI call.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from tests.spike.fsm_continuity_compaction.continuity_pipeline import backfill_and_compact

SESSION_ID = "spike-driver-session"

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


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        db = tmp_path / "history.db"
        jsonl_path = tmp_path / f"{SESSION_ID}.jsonl"
        jsonl_path.write_text("\n".join(_transcript_lines()) + "\n", encoding="utf-8")

        with patch("little_loops.session_store.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = json.dumps(
                {"type": "result", "subtype": "success", "result": "Mocked summary text."}
            )
            mock_run.return_value.stderr = ""
            result = backfill_and_compact(
                db,
                SESSION_ID,
                jsonl_path,
                config={"history": {"compaction": {"enabled": True, "budget_tokens": 50}}},
            )

    print("summary_text:", result.summary_text if result else None)


if __name__ == "__main__":
    main()
