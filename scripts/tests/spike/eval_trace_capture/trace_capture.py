"""Spike: prove live ordered tool-call trace extraction from stream-json lines.

Proves the FEAT-2878 outcome-risk mechanism in isolation: that walking
``assistant`` event ``message.content`` blocks for ``type == "tool_use"``,
in the same per-line JSON shape ``subprocess_utils.run_claude_command()``
already parses, yields a correctly ordered trace and can invoke a callback
live (not just after the fact). See ``.ll/spikes/spike-FEAT-2878.md``.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolCall:
    index: int
    name: str
    input: dict[str, Any]


def extract_tool_calls(
    stream_lines: Iterable[str],
    on_tool_call: Callable[[ToolCall], None] | None = None,
) -> list[ToolCall]:
    """Parse stream-json lines and return an ordered ToolCall trace.

    Mirrors the text-extraction branch in
    ``subprocess_utils.run_claude_command()`` (``etype == "assistant"``,
    ``block.get("type")`` filter) but collects ``tool_use`` blocks instead
    of ``text`` blocks, invoking ``on_tool_call`` synchronously per call.
    """
    calls: list[ToolCall] = []
    for line in stream_lines:
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            continue
        if event.get("type") != "assistant":
            continue
        msg = event.get("message", {})
        for block in msg.get("content", []):
            if block.get("type") != "tool_use":
                continue
            call = ToolCall(
                index=len(calls),
                name=block.get("name", ""),
                input=block.get("input", {}),
            )
            calls.append(call)
            if on_tool_call:
                on_tool_call(call)
    return calls
