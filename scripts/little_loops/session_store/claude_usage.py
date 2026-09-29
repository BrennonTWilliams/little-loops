"""Claude transcript producer qualification for newly ingested raw events.

The returned marker is persisted on ``raw_events`` at ingest time. Replay
must copy that persisted value; re-evaluating old payloads during rebuild
would incorrectly promote legacy observations that lacked producer evidence.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

CLAUDE_USAGE_CONTRACT = "claude-code/2.1.284"
_COMPONENTS = (
    "input_tokens",
    "output_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
)


def claude_transcript_contract(
    record: Mapping[str, Any], *, host: str | None, host_basis: str | None
) -> str | None:
    """Return the versioned contract marker for an eligible new raw record.

    Host attribution comes from the source handle, not the Claude-shaped
    payload. The observed 2.1.284 producer records carry version, session and
    message IDs plus four disjoint integer token components. A missing ID,
    incomplete component, or unverified version stays unknown.
    """
    if host != "claude-code" or host_basis != "handle":
        return None
    if record.get("type") != "assistant" or record.get("version") != "2.1.284":
        return None
    if not isinstance(record.get("sessionId"), str) or not record["sessionId"]:
        return None
    message = record.get("message")
    if not isinstance(message, Mapping):
        return None
    if not isinstance(message.get("id"), str) or not message["id"]:
        return None
    usage = message.get("usage")
    if not isinstance(usage, Mapping):
        return None
    values = [usage.get(name) for name in _COMPONENTS]
    if not all(type(value) is int and value >= 0 for value in values):
        return None
    if not any(values):
        return None
    return CLAUDE_USAGE_CONTRACT
