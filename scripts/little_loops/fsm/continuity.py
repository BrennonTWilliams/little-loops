"""FSM-side continuity-chain compaction wiring (FEAT-2711).

Promoted from ``scripts/tests/spike/fsm_continuity_compaction/continuity_pipeline.py``
per the spike's Promotion note, adapted to call FEAT-2747's assistant-inclusive
``compact_result_for_session_with_reasoning`` instead of the spike's bare
``compact_session()``/``compact_result_for_session()`` — the spike proved those
summarize only the already-known user prompt, never the state's own derived
reasoning, which is what a continuity-chain hop actually needs to carry forward.
"""

from __future__ import annotations

from pathlib import Path

from little_loops.compaction.result import CompactResult, compact_result_for_session_with_reasoning
from little_loops.session_store import (
    _backfill_assistant_messages,
    _backfill_messages,
    connect,
    resolve_history_db,
)
from little_loops.user_messages import get_project_folder


def summarize_completed_state(
    session_id: str,
    *,
    db: Path | str | None = None,
    working_dir: Path | None = None,
    config: dict | None = None,
) -> CompactResult | None:
    """Backfill then compact one just-finished host-CLI session (FEAT-2711).

    Synchronous, same-process pipeline proven race-free by the spike
    (``TestBackfillThenCompact``): a session's JSONL transcript is already on
    disk by the time its ``run_claude_command()`` invocation returns, so
    backfill can run immediately with no polling/wait step.

    Returns ``None`` if the session's transcript can't be located on disk, or
    if it has zero rows in both ``message_events``/``assistant_messages`` once
    backfilled (nothing to summarize).
    """
    project_folder = get_project_folder(working_dir or Path.cwd())
    if project_folder is None:
        return None
    jsonl_path = project_folder / f"{session_id}.jsonl"
    if not jsonl_path.exists():
        return None

    resolved_db = resolve_history_db(db)
    conn = connect(resolved_db)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO sessions(session_id, jsonl_path) VALUES(?, ?)",
            (session_id, str(jsonl_path)),
        )
        _backfill_messages(conn, [jsonl_path])
        _backfill_assistant_messages(conn, [jsonl_path])
        conn.commit()
    finally:
        conn.close()

    return compact_result_for_session_with_reasoning(session_id, resolved_db, config=config)
