"""Qwen Code wire-format normalization (ENH-3166).

Qwen session JSONL (``~/.qwen/projects/<encoded>/chats/<id>.jsonl``, qwen
0.21.6) is Claude-shaped at the envelope level — ``uuid``/``parentUuid``/
``sessionId``/``timestamp``/``type``/``cwd`` all carry Claude's names, and
assistant records keep the envelope ``type: "assistant"`` — but diverges in
the message body:

- body key ``message.parts[]`` instead of ``message.content[]``
- text blocks ``{"text": …}`` (optionally ``"thought": true``) instead of
  ``{"type": "text", "text": …}``
- tool calls ``{"functionCall": {"id", "name", "args"}}`` instead of
  ``{"type": "tool_use", "id", "name", "input"}``
- tool results: top-level ``type: "tool_result"`` records with
  ``message.parts[].functionResponse`` plus a sibling top-level
  ``toolCallResult`` carrying ``status``/``error``/``errorType``
- assistant role ``"model"`` instead of ``"assistant"``
- a disjoint tool-name vocabulary (``run_shell_command`` vs ``Bash``, …)
- a ``provenance`` field (``real_user``/``assistant_output``/``tool_result``/
  ``system``) and user-record subtypes (``notification``,
  ``mid_turn_user_message``) that must not reach ``message_events`` — note
  the mid-turn subtype carries ``provenance: "real_user"`` too, so
  provenance alone is not a clean discriminator

:func:`normalize_qwen_record` maps one qwen record into the Claude-shaped
form the existing ``_backfill_*`` extractors already consume, or returns
``None`` when the record has no Claude-shaped equivalent. Applied read-time
inside ``_iter_events`` — ``raw_events`` keeps the verbatim source line.
Verified against ~10.9k real records; see
``thoughts/shared/research/2026-08-14-ENH-3166-qwen-wire-format.md``.
"""

from __future__ import annotations

import json

# qwen tool name → canonical Claude tool name (ENH-3166). Observed across
# 10,866 real 0.21.6 records; unmapped names (MCP tools, future natives)
# pass through unchanged so tool_events still records them.
QWEN_TOOL_NAMES: dict[str, str] = {
    "run_shell_command": "Bash",
    "edit": "Edit",
    "read_file": "Read",
    "write_file": "Write",
    "grep_search": "Grep",
    "glob": "Glob",
    "list_directory": "LS",
    "todo_write": "TodoWrite",
    "ask_user_question": "AskUserQuestion",
}

# Per-tool argument-key renames (qwen key → Claude key). Observed 0.21.6
# argument keys already match Claude's (command/file_path/pattern/path/…),
# so no renames are needed yet; the map exists so a future divergence is a
# table entry, not a code change.
QWEN_TOOL_ARG_KEYS: dict[str, dict[str, str]] = {}


def normalize_qwen_record(record: dict) -> dict | None:
    """Normalize one qwen record into Claude shape, or ``None`` to drop it.

    ``user`` records survive only when ``provenance == "real_user"`` AND no
    subtype is set (excludes ``notification`` — provenance ``system`` — and
    ``mid_turn_user_message`` — provenance ``real_user`` but subtyped).
    ``assistant`` and ``tool_result`` records are reshaped; ``system``
    records (all subtypes) have no Claude-shaped equivalent the extractors
    consume and are dropped. Envelope fields (``uuid``/``sessionId``/
    ``timestamp``/``cwd``/…) pass through untouched.
    """
    record_type = record.get("type")
    if record_type == "user":
        if record.get("provenance") != "real_user" or record.get("subtype"):
            return None
        parts = _message_parts(record)
        if parts is None:
            return None
        content = _normalize_parts(parts)
        if not content:
            return None
        normalized = dict(record)
        normalized["message"] = {"role": "user", "content": content}
        return normalized
    if record_type == "assistant":
        parts = _message_parts(record)
        if parts is None:
            return None
        content = _normalize_parts(parts)
        if not content:
            return None
        normalized = dict(record)
        normalized["message"] = {"role": "assistant", "content": content}
        return normalized
    if record_type == "tool_result":
        parts = _message_parts(record)
        if parts is None:
            return None
        call_result = record.get("toolCallResult")
        status = call_result.get("status") if isinstance(call_result, dict) else None
        call_id = call_result.get("callId") if isinstance(call_result, dict) else None
        blocks: list[dict] = []
        for part in parts:
            if not isinstance(part, dict):
                continue
            response = part.get("functionResponse")
            if not isinstance(response, dict):
                continue
            blocks.append(
                {
                    "type": "tool_result",
                    # toolCallResult carries the authoritative call id and
                    # status; functionResponse.id is the fallback.
                    "tool_use_id": call_id if call_id else response.get("id"),
                    "content": _response_text(response.get("response")),
                    "is_error": status == "error",
                }
            )
        if not blocks:
            return None
        normalized = dict(record)
        # Claude carries tool results inside user records.
        normalized["type"] = "user"
        normalized["message"] = {"role": "user", "content": blocks}
        return normalized
    return None


def qwen_skip_at_ingest(record: dict) -> bool:
    """Ingest-time volume guard for the qwen layout (see ``HostLayout``).

    ``subtype: "ui_telemetry"`` is ~47% of qwen record volume and feeds no
    rebuild consumer today (the ``usage_events`` stretch goal is deferred),
    so it never reaches ``raw_events``. Every other record family ingests
    verbatim.
    """
    return record.get("subtype") == "ui_telemetry"


def _message_parts(record: dict) -> list | None:
    """Return ``record.message.parts`` when it is a list, else ``None``."""
    message = record.get("message")
    if not isinstance(message, dict):
        return None
    parts = message.get("parts")
    return parts if isinstance(parts, list) else None


def _normalize_parts(parts: list) -> list[dict]:
    """Translate qwen ``parts`` blocks into Claude ``content`` blocks."""
    content: list[dict] = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        text = part.get("text")
        if isinstance(text, str):
            if part.get("thought"):
                content.append({"type": "thinking", "thinking": text})
            else:
                content.append({"type": "text", "text": text})
            continue
        call = part.get("functionCall")
        if not isinstance(call, dict):
            continue
        name = str(call.get("name") or "")
        args = call.get("args")
        renames = QWEN_TOOL_ARG_KEYS.get(name)
        if isinstance(args, dict) and renames:
            args = {renames.get(key, key): value for key, value in args.items()}
        content.append(
            {
                "type": "tool_use",
                "id": call.get("id"),
                "name": QWEN_TOOL_NAMES.get(name, name),
                "input": args,
            }
        )
    return content


def _response_text(response: object) -> object:
    """Render ``functionResponse.response`` as text.

    Success responses carry ``{"output": str}``; some failure paths carry a
    plain string (a repr'd dict). Both shapes appear in real 0.21.6 data.
    """
    if isinstance(response, dict):
        output = response.get("output")
        return str(output) if output is not None else json.dumps(response)
    if isinstance(response, str):
        return response
    return str(response)
