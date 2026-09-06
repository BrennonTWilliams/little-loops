"""omp (oh-my-pi) wire-format normalization (ENH-3394).

omp session JSONL (``~/.omp/agent/sessions/<encoded-cwd>/<ts>_<sessionId>.jsonl``,
omp 18.0.11 — see ``session-entries.ts``/``session-manager.ts`` in the vendored
``@oh-my-pi/pi-coding-agent`` package) differs from both Claude and gemini:

- physical line 1 is a fixed-width **title slot** (``{type: "title", ...}``),
  rewritten ahead of the session header on every save — it is not a header
  and carries no session id.
- the session **header** (``{type: "session", version?, id, title?,
  timestamp, cwd, parentSession?, ...}``) is the first ``type: "session"``
  line — no other line carries the session id, so normalization happens at
  the file level like gemini's, not per-record like qwen's.
- every conversational line is ``{type: "message", id, parentId, timestamp,
  message: AgentMessage}``. The message's own ``role`` is one of
  ``"user"``, ``"developer"``, ``"assistant"``, ``"toolResult"`` — not
  Claude's flat user/assistant split. ``assistant`` content carries
  ``toolCall`` blocks inline (``{type: "toolCall", id, name, arguments}``),
  but each tool's result is a **separate** ``toolResult``-role entry
  (``toolCallId``, ``toolName``, ``content``, ``isError``) rather than
  nested in the next user turn, unlike gemini's inline ``toolCalls[].result``.
- non-conversational entry types (``thinking_level_change``,
  ``model_change``, ``service_tier_change``, ``compaction``,
  ``branch_summary``, ``custom``, ``custom_message``, ``label``,
  ``title_change``, ``ttsr_injection``, ``session_init``, ``mode_change``,
  ``credential_pin``, ``reset_boundary``) carry no reusable message content
  and are skipped.
- ``developer``-role messages (injected system-style prompts, distinct from
  ``user``) are also skipped — no Claude-shaped role fits them and no
  downstream extractor needs them.

:func:`normalize_omp_session` reads one session file end-to-end and yields
Claude-shaped ``user``/``assistant`` records with ``sessionId`` stamped from
the header, splitting each ``toolResult`` entry into a synthetic Claude
``tool_result`` user turn (the same idea as gemini's inline-tool-call split,
just sourced from a separate physical entry instead of a nested field).

Verified 2026-09-06 against the vendored omp 18.0.11 source
(``scripts/little_loops/hooks/adapters/omp/node_modules/@oh-my-pi/pi-coding-agent/src/session/``).
This issue's own Program Design paraphrase (a bare ``{role, content}``
message shape) predates that verification; the real ``AgentMessage`` union
is richer, as described above — see the issue's Deviations note. omp has no
real session captures available on the ENH-3394 dev machine, so fixtures are
synthesized from these vendored types, not sanitized real captures.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path


def normalize_omp_session(path: Path) -> Iterator[dict]:
    """Yield Claude-shaped records from one omp session JSONL file.

    Scans every line for the first ``type: "session"`` record to capture the
    session id (tolerating a leading title-slot line, or its absence on a
    legacy file), then converts each ``type: "message"`` entry. Malformed
    lines are skipped, not raised — matches the tolerant-parse convention of
    the other file-level/record-level normalizers.
    """
    try:
        handle = path.open(encoding="utf-8")
    except OSError:
        return
    session_id: str | None = None
    with handle:
        for raw_line in handle:
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                entry = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            if not isinstance(entry, dict):
                continue
            entry_type = entry.get("type")
            if entry_type == "session":
                if session_id is None:
                    session_id = entry.get("id")
                continue
            if entry_type != "message":
                continue
            yield from _normalize_omp_message(entry, session_id)


def _normalize_omp_message(entry: dict, session_id: str | None) -> Iterator[dict]:
    """Translate one omp ``{type: "message", message: AgentMessage}`` entry."""
    message = entry.get("message")
    if not isinstance(message, dict):
        return
    role = message.get("role")
    entry_id = entry.get("id")
    timestamp = entry.get("timestamp")

    if role == "user":
        yield {
            "type": "user",
            "sessionId": session_id,
            "uuid": entry_id,
            "timestamp": timestamp,
            "message": {"role": "user", "content": _text_blocks(message.get("content"))},
        }
        return

    if role == "assistant":
        content: list[dict] = []
        for block in _as_list(message.get("content")):
            if not isinstance(block, dict):
                continue
            block_type = block.get("type")
            if block_type == "text" and isinstance(block.get("text"), str):
                content.append({"type": "text", "text": block["text"]})
            elif block_type == "toolCall":
                content.append(
                    {
                        "type": "tool_use",
                        "id": block.get("id"),
                        "name": block.get("name"),
                        "input": block.get("arguments"),
                    }
                )
        yield {
            "type": "assistant",
            "sessionId": session_id,
            "uuid": entry_id,
            "timestamp": timestamp,
            "message": {
                "role": "assistant",
                "model": message.get("model"),
                "content": content,
            },
        }
        return

    if role == "toolResult":
        result_text = "\n".join(
            block.get("text", "")
            for block in _as_list(message.get("content"))
            if isinstance(block, dict) and isinstance(block.get("text"), str)
        )
        yield {
            "type": "user",
            "sessionId": session_id,
            "timestamp": timestamp,
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": message.get("toolCallId"),
                        "content": result_text,
                        "is_error": bool(message.get("isError")),
                    }
                ],
            },
        }
        return

    # "developer" and any future role: no Claude-shaped equivalent, skip.


def _as_list(content: object) -> list:
    return content if isinstance(content, list) else []


def _text_blocks(content: object) -> list[dict]:
    """Map omp's ``content: string | (TextContent|ImageContent)[]`` to Claude text blocks."""
    if isinstance(content, str):
        return [{"type": "text", "text": content}] if content else []
    blocks: list[dict] = []
    for part in _as_list(content):
        if (
            isinstance(part, dict)
            and part.get("type") == "text"
            and isinstance(part.get("text"), str)
        ):
            blocks.append({"type": "text", "text": part["text"]})
    return blocks
