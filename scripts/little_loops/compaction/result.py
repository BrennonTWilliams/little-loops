"""CompactResult: a thin dataclass wrapper over existing summary_nodes rows (FEAT-2598).

No schema change — wraps the same ``summary_nodes``/``summary_spans`` rows the
existing LCM compaction surface (``session_store._compact_session_conn``)
already produces.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CompactResult:
    """Result of a compaction pass for one session.

    Attributes:
        summary_message: The per-session condensed summary text
            (``kind='condensed'``, ``level=0``), or ``None`` if the session has
            no condensed node yet.
        compacted_messages: ``message_events`` ids covered by the condensed
            node's leaf summaries.
        summary_text: Alias of ``summary_message`` for 6-section-schema callers.
        context_token_estimate: Estimated token count of ``summary_text``.
    """

    summary_message: str | None
    compacted_messages: list[int] = field(default_factory=list)
    summary_text: str | None = None
    context_token_estimate: int = 0


def compact_result_for_session(
    session_id: str,
    db: Path | str,
) -> CompactResult | None:
    """Build a ``CompactResult`` from a session's existing summary_nodes/summary_spans rows.

    Returns ``None`` if the session has no per-session condensed node
    (``kind='condensed'``, ``level=0``) — i.e. compaction has not run for it yet.
    """
    from little_loops.session_store import connect

    conn = connect(db)
    try:
        row = conn.execute(
            "SELECT content, tokens FROM summary_nodes"
            " WHERE session_id = ? AND kind = 'condensed' AND level = 0",
            (session_id,),
        ).fetchone()
        if row is None:
            return None

        leaf_ids = [
            r[0]
            for r in conn.execute(
                "SELECT id FROM summary_nodes WHERE session_id = ? AND kind = 'leaf'",
                (session_id,),
            ).fetchall()
        ]
        message_ids: list[int] = []
        if leaf_ids:
            placeholders = ",".join(["?"] * len(leaf_ids))
            message_ids = [
                r[0]
                for r in conn.execute(
                    "SELECT DISTINCT message_event_id FROM summary_spans"
                    f" WHERE summary_id IN ({placeholders}) ORDER BY message_event_id",
                    leaf_ids,
                ).fetchall()
            ]

        content, tokens = row[0], row[1] or 0
        return CompactResult(
            summary_message=content,
            compacted_messages=message_ids,
            summary_text=content,
            context_token_estimate=tokens,
        )
    finally:
        conn.close()
