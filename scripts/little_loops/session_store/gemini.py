"""Gemini CLI wire-format normalization (ENH-3393).

Gemini session JSONL (``~/.gemini/tmp/<project-id>/chats/session-*.jsonl``,
gemini-cli 0.46.0) is a different shape from both Claude and qwen:

- line 1 is a session **header** (``{sessionId, projectHash, startTime,
  lastUpdated, kind}``) — no other line carries ``sessionId``, so normalization
  must happen at the file level, not per-record (unlike qwen's
  :func:`~little_loops.session_store.qwen.normalize_qwen_record`).
- the initial user turn (session-context preamble) is nested inside the
  first ``{"$set": {"messages": [...]}}}`` patch record; every later turn is a
  bare top-level ``{id, timestamp, type: "user" | "gemini", content, ...}``
  record. Later ``$set`` patches only touch metadata (``lastUpdated``,
  ``memoryScratchpad``) and carry no messages.
- ``{"$rewindTo": "<message id>"}`` records mark a rewind point and carry no
  message content of their own.
- assistant (``"gemini"``) turns carry tool calls **inline** as
  ``toolCalls: [{id, name, args, result, resultDisplay, status, ...}]``
  rather than as separate ``tool_use``/``tool_result`` records.

:func:`normalize_gemini_session` reads one session file end-to-end and yields
Claude-shaped ``user``/``assistant`` records with ``sessionId`` stamped from
the header, splitting each inline tool call into a Claude ``tool_use`` block
on the assistant turn plus a synthetic Claude ``tool_result`` user turn.
Legacy single-document ``chats/session-*.json`` files (whole ``messages[]``
array, pre-Oct-2025) are out of scope — they don't match the ``*.jsonl``
session glob, so they never reach this reader.

Verified 2026-09-06 against gemini-cli 0.46.0 (installed) and real captures
under ``~/.gemini/tmp/``; see ENH-3393's "Verified Host Layouts".
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path


def normalize_gemini_session(path: Path) -> Iterator[dict]:
    """Yield Claude-shaped records from one gemini session JSONL file.

    Reads the header line for ``sessionId``, then walks the remaining lines:
    the first ``$set.messages`` array (initial session-context turn), bare
    ``user``/``gemini`` message records, and skips ``$rewindTo`` markers and
    metadata-only ``$set`` patches. Malformed lines are skipped, not raised —
    matches the tolerant-parse convention of the per-record normalizers.
    """
    try:
        handle = path.open(encoding="utf-8")
    except OSError:
        return
    session_id: str | None = None
    with handle:
        for line_no, raw_line in enumerate(handle, start=1):
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                record = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            if not isinstance(record, dict):
                continue
            if line_no == 1:
                session_id = record.get("sessionId")
                continue
            if "$rewindTo" in record:
                continue
            if "$set" in record:
                set_value = record["$set"]
                messages = set_value.get("messages") if isinstance(set_value, dict) else None
                if isinstance(messages, list):
                    for message in messages:
                        yield from _normalize_gemini_message(message, session_id)
                continue
            if record.get("type") in ("user", "gemini"):
                yield from _normalize_gemini_message(record, session_id)


def _normalize_gemini_message(message: dict, session_id: str | None) -> Iterator[dict]:
    """Translate one gemini message record into Claude-shaped record(s)."""
    message_type = message.get("type")
    timestamp = message.get("timestamp")
    content = _text_blocks(message.get("content"))

    if message_type == "user":
        yield {
            "type": "user",
            "sessionId": session_id,
            "uuid": message.get("id"),
            "timestamp": timestamp,
            "message": {"role": "user", "content": content},
        }
        return

    if message_type != "gemini":
        return

    tool_calls = message.get("toolCalls")
    tool_calls = tool_calls if isinstance(tool_calls, list) else []
    for call in tool_calls:
        if not isinstance(call, dict):
            continue
        content.append(
            {
                "type": "tool_use",
                "id": call.get("id"),
                "name": call.get("name"),
                "input": call.get("args"),
            }
        )

    yield {
        "type": "assistant",
        "sessionId": session_id,
        "uuid": message.get("id"),
        "timestamp": timestamp,
        "message": {
            "role": "assistant",
            "model": message.get("model"),
            "content": content,
        },
    }

    result_blocks = [
        {
            "type": "tool_result",
            "tool_use_id": call.get("id"),
            "content": _tool_result_text(call.get("result"), call.get("resultDisplay")),
            "is_error": call.get("status") == "error",
        }
        for call in tool_calls
        if isinstance(call, dict)
    ]
    if result_blocks:
        yield {
            "type": "user",
            "sessionId": session_id,
            "timestamp": tool_calls[-1].get("timestamp") if tool_calls else timestamp,
            "message": {"role": "user", "content": result_blocks},
        }


def _text_blocks(content: object) -> list[dict]:
    """Map gemini ``content: [{"text": ...}]`` parts into Claude text blocks."""
    blocks: list[dict] = []
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                blocks.append({"type": "text", "text": part["text"]})
    return blocks


def _tool_result_text(result: object, result_display: object) -> str:
    """Render a gemini tool call's result as text for a Claude tool_result block.

    ``result`` is Gemini API function-response shape
    (``[{"functionResponse": {"response": ...}}]``); ``resultDisplay`` is a
    pre-rendered markdown/string fallback used when ``result`` can't be
    flattened to text.
    """
    if isinstance(result, list):
        texts = []
        for item in result:
            if not isinstance(item, dict):
                continue
            response = item.get("functionResponse")
            if isinstance(response, dict):
                payload = response.get("response")
                texts.append(payload if isinstance(payload, str) else json.dumps(payload))
        if texts:
            return "\n".join(texts)
    if isinstance(result_display, str):
        return result_display
    return json.dumps(result) if result is not None else ""
