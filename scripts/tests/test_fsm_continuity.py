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
from little_loops.user_messages import encode_project_path

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
        with patch("little_loops.fsm.continuity.get_sessions_folder", return_value=None):
            result = summarize_completed_state(SESSION_ID, db=tmp_path / "history.db")
        assert result is None

    def test_returns_none_when_transcript_missing(self, tmp_path: Path) -> None:
        """Project folder exists but has no matching <session_id>.jsonl -> None."""
        project_folder = tmp_path / "project"
        project_folder.mkdir()
        with patch("little_loops.fsm.continuity.get_sessions_folder", return_value=project_folder):
            result = summarize_completed_state(SESSION_ID, db=tmp_path / "history.db")
        assert result is None

    def test_backfills_and_compacts_with_assistant_content(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """The assistant-inclusive summary carries forward both user and assistant turns.

        LL_HOST_CLI is pinned so the ``-p``-flag prompt inspection is
        deterministic: resolve_host() otherwise reads worker env/PATH, which a
        co-resident xdist test can leave in a state that routes the summarizer
        to a non-claude host (no ``-p``) or to fail-soft truncation (no CLI
        call at all).
        """
        monkeypatch.setenv("LL_HOST_CLI", "claude-code")
        db = tmp_path / "history.db"
        project_folder = tmp_path / "project"
        project_folder.mkdir()
        _write_transcript(project_folder)

        with patch("little_loops.fsm.continuity.get_sessions_folder", return_value=project_folder):
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

    def test_resolves_qwen_chats_transcript(self, tmp_path: Path, monkeypatch) -> None:
        """ENH-3165: under LL_HOOK_HOST=qwen the transcript is located under the
        project root's ``chats/`` subdir, not at the root itself."""
        monkeypatch.setenv("LL_HOOK_HOST", "qwen")
        monkeypatch.setenv("LL_HOST_CLI", "claude-code")
        fake_home = tmp_path / "home"
        encoded = encode_project_path(str(tmp_path.resolve()))
        chats_dir = fake_home / ".qwen" / "projects" / encoded / "chats"
        chats_dir.mkdir(parents=True)
        _write_transcript(chats_dir)
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.chdir(tmp_path)

        db = tmp_path / "history.db"
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

        # Reaching the transcript at all is the assertion target — a None here
        # means the qwen chats/ join regressed (fail-soft None contract).
        assert result is not None
