"""Spike: prove a host CLI session ID can be captured from stream-json output.

FEAT-2711 Option B needs the FSM layer to know *which* session it just ran, to
key `compact_session()`/`compact_result_for_session()`. `run_claude_command()`
(scripts/little_loops/subprocess_utils.py) already parses the same
`system`/`init` stream-json event for `model` but discards `session_id`. This
module proves the field is present and parseable — it does not modify
production code.
"""

from __future__ import annotations

import json


def parse_session_id_from_stream_json(line: str) -> str | None:
    """Extract ``session_id`` from a ``system``/``init`` stream-json event line.

    Mirrors the event-shape check `run_claude_command()` already performs
    (``event.get("type") == "system" and event.get("subtype") == "init"``).
    Returns ``None`` for any other event type, or malformed JSON.
    """
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        return None
    if event.get("type") != "system" or event.get("subtype") != "init":
        return None
    session_id = event.get("session_id")
    return str(session_id) if session_id else None
