"""File I/O helpers for workflow sequence analysis."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import yaml


def _load_messages(messages_file: Path) -> list[dict[str, Any]]:
    """Load messages from JSONL file."""
    messages = []
    skipped = 0
    with open(messages_file, encoding="utf-8") as f:
        for line_num, raw_line in enumerate(f, 1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                messages.append(json.loads(line))
            except json.JSONDecodeError as e:
                skipped += 1
                print(f"Warning: skipping malformed line {line_num}: {e}", file=sys.stderr)
    if skipped:
        print(f"Warning: skipped {skipped} malformed line(s) in {messages_file}", file=sys.stderr)
    return messages


def _load_messages_from_db(db_path: Path) -> list[dict[str, Any]]:
    """Load user messages from the unified session DB (ENH-1621).

    Reads ``message_events`` rows seeded by
    :func:`little_loops.session_store._backfill_messages` and shapes them like
    the JSONL records :func:`_load_messages` returns so the rest of
    :func:`analyze_workflows` consumes them unchanged.

    Returns ``[]`` when the DB is missing, the table is empty, or the schema
    pre-dates the v2 migration — the caller treats an empty result as the
    fallback trigger.
    """
    if not db_path.exists():
        return []
    try:
        from little_loops.session_store import connect

        conn = connect(db_path)
    except Exception:  # pragma: no cover - defensive
        return []
    try:
        try:
            rows = conn.execute(
                "SELECT id, ts, session_id, content FROM message_events ORDER BY id"
            ).fetchall()
        except Exception:
            return []
    finally:
        conn.close()
    messages: list[dict[str, Any]] = []
    for row in rows:
        messages.append(
            {
                "uuid": f"msg-{row['id']}",
                "timestamp": row["ts"],
                "session_id": row["session_id"],
                "content": row["content"] or "",
                "git_branch": None,
            }
        )
    return messages


def _load_patterns(patterns_file: Path) -> dict[str, Any]:
    """Load patterns from Step 1 YAML output."""
    with open(patterns_file, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
