"""Isolated proof of the `defer_loading` + tool-search-tool request shape.

Deliberately does not import `little_loops.tool_catalog` or
`little_loops.host_runner` — see `test_spike_does_not_import_tool_catalog_or_host_runner`.
Mirrors their assembly logic against the real installed `anthropic` SDK types
so a shape mismatch here would also break the real integration.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SEARCH_TOOL_NAME = "tool_search_tool_bm25"
SEARCH_TOOL_TYPE = "tool_search_tool_bm25_20251119"


@dataclass(frozen=True)
class SpikeToolEntry:
    name: str
    description: str
    input_schema: dict[str, Any]


def assemble_deferred_tools(
    entries: list[SpikeToolEntry],
    *,
    defer_threshold: int,
) -> list[dict[str, Any]]:
    """Serialize entries to tool dicts, flagging `defer_loading` above threshold.

    Entries at index >= defer_threshold get `defer_loading: True`. If any
    entry ends up deferred, prepends exactly one search-tool entry so
    `defer_loading` has an effect (per the SDK contract: a deferred tool
    with no search tool present is inert). Returns plain dicts shaped as
    `anthropic.types.ToolParam` / `ToolSearchToolBm25_20251119Param`.
    """
    tools: list[dict[str, Any]] = []
    any_deferred = False
    for index, entry in enumerate(entries):
        tool: dict[str, Any] = {
            "name": entry.name,
            "description": entry.description,
            "input_schema": entry.input_schema,
        }
        if index >= defer_threshold:
            tool["defer_loading"] = True
            any_deferred = True
        tools.append(tool)

    if any_deferred:
        search_tool: dict[str, Any] = {"name": SEARCH_TOOL_NAME, "type": SEARCH_TOOL_TYPE}
        tools.insert(0, search_tool)

    return tools


def validates_as_tool_param(tool_dict: dict[str, Any]) -> bool:
    """True if `tool_dict` round-trips through the SDK's `ToolParam` shape."""
    import pydantic
    from anthropic.types import ToolParam

    try:
        pydantic.TypeAdapter(ToolParam).validate_python(tool_dict)
    except pydantic.ValidationError:
        return False
    return True


def validates_as_search_tool_param(tool_dict: dict[str, Any]) -> bool:
    """True if `tool_dict` round-trips through the SDK's BM25 search-tool shape."""
    import pydantic
    from anthropic.types.tool_search_tool_bm25_20251119_param import (
        ToolSearchToolBm25_20251119Param,
    )

    try:
        pydantic.TypeAdapter(ToolSearchToolBm25_20251119Param).validate_python(tool_dict)
    except pydantic.ValidationError:
        return False
    return True
