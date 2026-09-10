"""Codex exec-call normalization to Claude shape (ENH-3433).

Codex rollout JSONL (``~/.codex/sessions/**/*.jsonl``, codex-cli 0.152.1) is
envelope-shaped, not Claude-shaped: every line is
``{"timestamp", "type", "payload": {...}}`` and the ``payload`` carries a
second, host-native subtype vocabulary of its own. Unlike qwen/gemini/omp,
no normalizer previously existed for Codex — ``parse_codex_rollout`` passed
every line through untouched, so every ll-signal reader in ``cli/logs.py``
(all keyed on Claude record shape) saw zero events from a Codex session.

This module normalizes exactly the shell-exec subset of that vocabulary —
the only subset ``cli/logs.py``'s readers need — leaving every other record
type to pass through untouched (unlike qwen, where ``None`` means *drop*;
here it means *pass the raw envelope through*, since most Codex record
types have no Claude-shaped equivalent to normalize into and still carry
information downstream consumers such as ``cli/ctx_stats.py``'s
``_codex_cache_usage`` (``event_msg``/``token_count``) or
``user_messages.py::_extract_codex_user_messages`` rely on).

**Observed shapes (survey, 2026-09-10; n=3 exec calls across 8,859 rollouts
on the dev machine — see ENH-3433's Current Behavior for the full survey).**
A shell command runs as three envelopes, observed in this order on every
sample:

1. ``response_item``/``custom_tool_call`` (``name == "exec"``) — a
   model-authored JS snippet in ``payload.input`` calling
   ``tools.exec_command({cmd: "...", ...})``. The literal shell command is
   only recoverable by parsing this JS text (:func:`_extract_exec_cmd`).
2. ``event_msg``/``item_completed`` with ``item.type == "CommandExecution"``
   — the *actual* parsed shell invocation: ``item.command`` (e.g.
   ``["/bin/zsh", "-lc", "<cmd>"]``), ``status``
   (``"completed"``/``"failed"``), ``exit_code``, plus ``stdout``/``stderr``/
   ``aggregated_output``. This item's own ``id`` (``exec-<uuid>``) shares no
   key with the ``custom_tool_call``'s ``call_id`` — pairing is by matching
   ``item.command``'s shell text against the pending call's extracted cmd
   (falling back to the most recently pending call when no cmd matches).
3. ``response_item``/``custom_tool_call_output`` — the tool's own report,
   always the constant header ``"Script completed\\nWall time N
   seconds\\nOutput:\\n"`` followed by whatever the model chose to
   ``text()``. **This header is identical whether the shell command
   succeeded or failed** (verified on fixture line 14, a failed
   ``rg``/``sed`` pipeline with ``exit_code: 1`` — its output at line 15 has
   the exact same header as every successful call's). The only failure
   signal that exists anywhere in the three envelopes is
   ``CommandExecution.status``/``exit_code`` — never the output text.

:class:`CodexNormalizer` maps envelope 1 to a Claude ``assistant`` record
carrying one ``tool_use`` block (``name: "Bash"``), records envelope 2's
status keyed by the matched ``call_id`` without emitting anything, and maps
envelope 3 to a Claude ``user`` record carrying one ``tool_result`` block
whose ``is_error`` is ``True`` (and only present at all) when the matched
status was a failure. Every other envelope returns ``None``, which callers
must treat as "yield the raw envelope unchanged" — the opposite convention
from :func:`little_loops.session_store.qwen.normalize_qwen_record`.
"""

from __future__ import annotations

import json
import re
import shlex

_CMD_RE = re.compile(r"cmd:\s*([\"'`])((?:(?!\1)[^\\]|\\.)*)\1", re.DOTALL)

_SCRIPT_HEADER_RE = re.compile(r"^Script completed\nWall time [\d.]+ seconds\nOutput:\n$")


def _extract_exec_cmd(js_snippet: str) -> str | None:
    """Extract the unescaped ``cmd:`` shell text from a ``tools.exec_command({...})``
    snippet, or ``None`` when no ``cmd:`` value is found.

    Tolerates double-quoted, single-quoted, and backtick-delimited values —
    the snippet is model-authored, and n=3 from a single session is not
    enough to assume double quotes forever. The captured group carries
    JS-style escapes, which coincide with JSON escapes for everything a
    model emits in practice; unescape via ``json.loads``, falling back to
    the raw capture on failure (never raise).
    """
    m = _CMD_RE.search(js_snippet)
    if not m:
        return None
    quote, captured = m.group(1), m.group(2)
    if quote == '"':
        try:
            return json.loads('"' + captured + '"')
        except ValueError:
            return captured
    # Single-quote/backtick: turn the delimiter-specific escape into a
    # literal quote, escape any embedded double-quote so the JSON-escape
    # reuse below doesn't choke on it, then unescape the rest as JSON.
    unescaped_delim = captured.replace("\\" + quote, quote).replace('"', '\\"')
    try:
        return json.loads('"' + unescaped_delim + '"')
    except ValueError:
        return captured


def _command_text(command: list) -> str:
    """Render a ``CommandExecution.command`` list as shell text.

    ``["/bin/zsh", "-lc", "<cmd>"]`` (observed on 0.152.1) yields ``<cmd>``
    verbatim; any other shape is rendered via ``shlex.join`` as a
    best-effort fallback.
    """
    if len(command) == 3 and command[1] == "-lc":
        return str(command[-1])
    return shlex.join(str(c) for c in command)


class CodexNormalizer:
    """Stateful per-envelope Codex-exec-to-Claude-shape normalizer.

    One instance per rollout file — construct with the session's
    ``session_id``/``cwd`` (read from line 1's ``session_meta`` payload by
    the caller) and call once per envelope in file order. Internal state
    (``_pending``, ``_status``) tracks the in-flight ``call_id -> cmd``
    mapping and the ``call_id -> failed`` flag between a ``custom_tool_call``
    and its eventual ``custom_tool_call_output``; both entries are popped
    once the output is emitted, so state stays bounded to in-flight calls.

    A single ``custom_tool_call`` can drive several ``tools.exec_command``
    calls (the ``exec`` tool is a JS runtime) and thus several
    ``CommandExecution`` items, all falling back to the same pending
    ``call_id`` when their ``command`` doesn't match the one extracted
    ``cmd:`` value. The failed flag is therefore OR-accumulated (sticky) per
    ``call_id`` — a later successful exec must not erase an earlier failure.
    """

    def __init__(self, *, session_id: str, cwd: str) -> None:
        self._session_id = session_id
        self._cwd = cwd
        self._pending: dict[str, str] = {}
        self._status: dict[str, bool] = {}

    def __call__(self, envelope: dict) -> dict | None:
        """Normalize one envelope, or return ``None`` to pass it through untouched."""
        record_type = envelope.get("type")
        payload = envelope.get("payload")
        if not isinstance(payload, dict):
            return None
        subtype = payload.get("type")

        if record_type == "response_item" and subtype == "custom_tool_call":
            if payload.get("name") != "exec":
                return None
            return self._normalize_call(envelope, payload)

        if record_type == "response_item" and subtype == "custom_tool_call_output":
            return self._normalize_output(envelope, payload)

        if record_type == "event_msg" and subtype == "item_completed":
            self._record_command_execution(payload)
            return None

        return None

    def _normalize_call(self, envelope: dict, payload: dict) -> dict:
        call_id = str(payload.get("call_id") or "")
        raw_input = payload.get("input")
        js_snippet = raw_input if isinstance(raw_input, str) else ""
        cmd = _extract_exec_cmd(js_snippet)
        command_text = cmd if cmd is not None else js_snippet
        if call_id:
            self._pending[call_id] = command_text
        return {
            "type": "assistant",
            "timestamp": envelope.get("timestamp", ""),
            "sessionId": self._session_id,
            "cwd": self._cwd,
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": call_id,
                        "name": "Bash",
                        "input": {"command": command_text},
                    }
                ],
            },
        }

    def _record_command_execution(self, payload: dict) -> None:
        item = payload.get("item")
        if not isinstance(item, dict) or item.get("type") != "CommandExecution":
            return
        command = item.get("command")
        command_text = _command_text(command) if isinstance(command, list) else None
        failed = item.get("status") == "failed" or item.get("exit_code") not in (0, None)

        call_id = None
        if command_text is not None:
            for pending_id, pending_cmd in self._pending.items():
                if pending_cmd == command_text:
                    call_id = pending_id
                    break
        if call_id is None and self._pending:
            call_id = next(reversed(self._pending))
        if call_id is None:
            return
        self._status[call_id] = self._status.get(call_id, False) or failed

    def _normalize_output(self, envelope: dict, payload: dict) -> dict:
        call_id = str(payload.get("call_id") or "")
        output = payload.get("output")
        blocks = output if isinstance(output, list) else []
        texts: list[str] = [
            block["text"]
            for block in blocks
            if isinstance(block, dict) and isinstance(block.get("text"), str)
        ]
        if texts and _SCRIPT_HEADER_RE.match(texts[0]):
            texts = texts[1:]
        content = [{"type": "text", "text": text} for text in texts]

        result_block: dict = {
            "type": "tool_result",
            "tool_use_id": call_id,
            "content": content,
        }
        failed = self._status.pop(call_id, None)
        self._pending.pop(call_id, None)
        if failed:
            # Literal True only — never a truthy string/int, and never set
            # to False (a successful paired exec omits the key entirely).
            result_block["is_error"] = True

        return {
            "type": "user",
            "timestamp": envelope.get("timestamp", ""),
            "sessionId": self._session_id,
            "cwd": self._cwd,
            "message": {
                "role": "user",
                "content": [result_block],
            },
        }
