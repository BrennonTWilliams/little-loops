"""Spike: prove the backfill -> compact -> summary pipeline for one just-finished session.

Exercises the real production functions (`session_store._backfill_messages`,
`session_store._backfill_assistant_messages`, `session_store.compact_session`,
`compaction.result.compact_result_for_session`) against a hand-written JSONL
transcript fixture, in-process, with no intervening `ll-session backfill` CLI
call and no real host CLI invocation. Proves whether a same-run synchronous
call is viable, and — separately — whether the resulting summary captures
assistant-authored content or only the user turn.
"""

from __future__ import annotations

from pathlib import Path

from little_loops.compaction.result import CompactResult, compact_result_for_session
from little_loops.session_store import (
    _backfill_assistant_messages,
    _backfill_messages,
    compact_session,
    connect,
)


def backfill_and_compact(
    db: Path,
    session_id: str,
    jsonl_path: Path,
    *,
    config: dict | None = None,
) -> CompactResult | None:
    """Seed ``sessions``/``message_events``/``assistant_messages`` from *jsonl_path*,
    then run ``compact_session`` + ``compact_result_for_session`` — same process,
    no async step, no external CLI call.
    """
    conn = connect(db)
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

    compact_session(session_id, db, config=config)
    return compact_result_for_session(session_id, db)
